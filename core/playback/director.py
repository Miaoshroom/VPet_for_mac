"""动画调度与互动编排"""

from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtCore import QObject, pyqtSignal

from core.playback.catalog import AnimationCatalog, DEFAULT_PET_STATE, validate_pet_state
from core.playback.clip import Clip, Mode
from core.playback.flipbook import FlipbookPlayer


class PressHoldAnimator(QObject):
    """按住互动动画"""

    frame_changed = pyqtSignal(object)

    def __init__(
        self,
        start: Clip,
        loop: Clip,
        end: Clip,
        parent: QObject | None = None,
        *,
        mode_factory: Callable[[], Mode] | None = None,
    ) -> None:
        super().__init__(parent)
        self._start_c = start
        self._loop_c = loop
        self._end_c = end
        self._mode_factory = mode_factory
        self._player = FlipbookPlayer(self)
        self._player.frame_changed.connect(self.frame_changed)
        self._on_resume: Callable[[], None] | None = None
        self._wants_end = False
        self._phase = "idle"

    def start(self, on_resume: Callable[[], None] | None = None) -> None:
        self._player.stop()
        self._player.disconnect_finished()
        self._on_resume = on_resume
        self._wants_end = False
        self._phase = "start"
        self._player.finished.connect(self._after_start)
        self._player.play(self._start_c, loop=False)

    def end(self) -> None:
        if self._phase in ("end", "idle"):
            return
        self._wants_end = True
        if self._phase == "loop":
            self._play_end()

    def stop(self) -> None:
        self._player.stop()
        self._player.disconnect_finished()
        self._on_resume = None
        self._wants_end = False
        self._phase = "idle"

    def is_active(self) -> bool:
        return self._phase != "idle"

    def _after_start(self) -> None:
        self._player.disconnect_finished()
        if self._wants_end:
            self._play_end()
            return
        self._play_loop(refresh=False)

    def _after_loop(self) -> None:
        self._player.disconnect_finished()
        if self._wants_end:
            self._play_end()
            return
        self._play_loop(refresh=True)

    def _play_loop(self, *, refresh: bool) -> None:
        self._phase = "loop"
        if refresh:
            self._refresh_loop_mode()
        self._player.stop()
        self._player.disconnect_finished()
        self._player.finished.connect(self._after_loop)
        self._player.play(self._loop_c, loop=False)

    def _refresh_loop_mode(self) -> None:
        if self._mode_factory is None:
            return
        try:
            mode = self._mode_factory()
        except KeyError:
            return
        self._loop_c = mode.loop
        if mode.end is not None:
            self._end_c = mode.end

    def _play_end(self) -> None:
        self._phase = "end"
        self._player.stop()
        self._player.disconnect_finished()
        self._player.finished.connect(self._to_idle)
        self._player.play(self._end_c, loop=False)

    def _to_idle(self) -> None:
        self._player.disconnect_finished()
        self._phase = "idle"
        self._wants_end = False
        callback = self._on_resume
        self._on_resume = None
        if callback is not None:
            callback()


class PetAnimationDirector(QObject):
    """调度当前动作切换和按住互动"""

    frame_changed = pyqtSignal(object)

    def __init__(
        self,
        modes: dict[str, Mode],
        default_mode: str,
        interactions: dict[str, PressHoldAnimator],
        default_interaction: str,
        parent: QObject | None = None,
        *,
        animation_catalog: AnimationCatalog | None = None,
        pet_state: str = DEFAULT_PET_STATE,
    ) -> None:
        super().__init__(parent)
        if not modes:
            raise ValueError("必须至少提供一个可切换动作")
        if default_mode not in modes:
            raise ValueError(f"默认动作不存在: {default_mode}")
        if default_interaction not in interactions and default_interaction not in modes:
            raise ValueError(f"默认互动不存在: {default_interaction}")
        self._modes = modes
        self._animation_catalog = animation_catalog
        self._pet_state = validate_pet_state(pet_state)
        self._default_mode = default_mode
        self._current_mode = default_mode
        self._current_mode_obj: Mode = self._resolve_mode(default_mode)
        self._pending_mode: str | None = None
        self._phase = "idle"
        self._interactions = interactions
        self._default_interaction = default_interaction
        self._active_interaction_name: str | None = None
        self._active_interaction: PressHoldAnimator | None = None
        self._transient_interaction: PressHoldAnimator | None = None
        self._mode_player = FlipbookPlayer(self)
        self._mode_player.frame_changed.connect(self.frame_changed)
        for interaction in self._interactions.values():
            interaction.frame_changed.connect(self.frame_changed)

    def current_mode_name(self) -> str:
        return self._pending_mode or self._current_mode

    def current_mode(self) -> Mode:
        return self._current_mode_obj

    def pet_state(self) -> str:
        return self._pet_state

    def set_pet_state(self, pet_state: str) -> None:
        self._pet_state = validate_pet_state(pet_state)
        if not self.is_interaction_active():
            self.resume_mode(self._current_mode)

    def is_press_active(self) -> bool:
        return self.is_interaction_active()

    def is_interaction_active(self) -> bool:
        return self._active_interaction is not None

    def start_default_mode(self) -> None:
        self._start_mode(self._default_mode)

    def switch_mode(self, mode_name: str) -> None:
        if mode_name not in self._modes:
            raise KeyError(f"未知动作: {mode_name}")
        if mode_name == self.current_mode_name():
            return
        if self.is_interaction_active():
            self._current_mode = mode_name
            self._current_mode_obj = self._resolve_mode(mode_name)
            self._pending_mode = None
            return

        mode = self.current_mode()
        if mode.is_phased:
            self._pending_mode = mode_name
            if self._phase == "loop":
                self._play_current_end()
            return
        self._start_mode(mode_name)

    def on_mouse_press(self) -> None:
        self.start_interaction(self._default_interaction)

    def on_mouse_release(self) -> None:
        self.end_interaction()

    def start_interaction(self, interaction_name: str) -> None:
        if not self._has_action(interaction_name):
            raise KeyError(f"未知互动: {interaction_name}")
        if self.is_interaction_active():
            return
        try:
            interaction = self._interaction_for(interaction_name)
        except KeyError:
            # 当前状态没有该互动素材时忽略本次互动，等待素材提供对应状态或 any
            return
        self._stop_mode_player()
        self._pending_mode = None
        self._active_interaction_name = interaction_name
        self._active_interaction = interaction
        interaction.start(on_resume=self._resume_current_mode)

    def end_interaction(self) -> None:
        if self._active_interaction is None:
            return
        self._active_interaction.end()

    def stop(self) -> None:
        self._stop_mode_player()
        for interaction in self._interactions.values():
            interaction.stop()
        if self._transient_interaction is not None:
            self._transient_interaction.stop()
        self._active_interaction = None
        self._active_interaction_name = None
        self._pending_mode = None
        self._phase = "idle"

    def resume_mode(self, mode_name: str | None = None) -> None:
        if mode_name is not None:
            if mode_name not in self._modes:
                raise KeyError(f"未知动作: {mode_name}")
            self._current_mode = mode_name
            self._current_mode_obj = self._resolve_mode(mode_name)
        self._resume_current_mode()

    def _resolve_mode(self, mode_name: str) -> Mode:
        if self._animation_catalog is not None:
            return self._animation_catalog.mode_for(mode_name, self._pet_state)
        return self._modes[mode_name]

    def _has_action(self, action_name: str) -> bool:
        if self._animation_catalog is not None:
            return self._animation_catalog.has_action(action_name)
        return action_name in self._interactions or action_name in self._modes

    def _interaction_for(self, interaction_name: str) -> PressHoldAnimator:
        if self._animation_catalog is None and interaction_name in self._interactions:
            return self._interactions[interaction_name]
        mode = self._resolve_mode(interaction_name)
        if not mode.is_phased or mode.start is None or mode.end is None:
            raise KeyError(f"互动动作必须是 phased: {interaction_name}")
        interaction = PressHoldAnimator(
            mode.start,
            mode.loop,
            mode.end,
            self,
            mode_factory=lambda: self._resolve_mode(interaction_name),
        )
        interaction.frame_changed.connect(self.frame_changed)
        self._transient_interaction = interaction
        return interaction

    def _stop_mode_player(self) -> None:
        self._mode_player.stop()
        self._mode_player.disconnect_finished()

    def _start_mode(self, mode_name: str) -> None:
        self._stop_mode_player()
        self._current_mode = mode_name
        self._current_mode_obj = self._resolve_mode(mode_name)
        self._pending_mode = None
        mode = self.current_mode()
        if mode.is_phased:
            self._phase = "start"
            assert mode.start is not None
            self._mode_player.finished.connect(self._after_mode_start)
            self._mode_player.play(mode.start, loop=False)
            return
        self._phase = "loop"
        self._play_current_loop(refresh=False)

    def _resume_current_mode(self) -> None:
        self._stop_mode_player()
        self._active_interaction = None
        self._active_interaction_name = None
        self._transient_interaction = None
        self._pending_mode = None
        self._phase = "loop"
        self._play_current_loop(refresh=False)

    def _after_mode_start(self) -> None:
        self._mode_player.disconnect_finished()
        if self._pending_mode is not None:
            self._play_current_end()
            return
        self._play_current_loop(refresh=False)

    def _after_mode_loop(self) -> None:
        self._mode_player.disconnect_finished()
        if self._pending_mode is not None:
            self._play_current_end()
            return
        self._play_current_loop(refresh=True)

    def _play_current_loop(self, *, refresh: bool = True) -> None:
        self._stop_mode_player()
        if refresh:
            self._current_mode_obj = self._resolve_mode(self._current_mode)
        self._phase = "loop"
        self._mode_player.finished.connect(self._after_mode_loop)
        self._mode_player.play(self.current_mode().loop, loop=False)

    def _play_current_end(self) -> None:
        mode = self.current_mode()
        if not mode.is_phased:
            next_mode = self._pending_mode
            self._pending_mode = None
            if next_mode is not None:
                self._start_mode(next_mode)
            return
        self._stop_mode_player()
        self._phase = "end"
        assert mode.end is not None
        self._mode_player.finished.connect(self._after_mode_end)
        self._mode_player.play(mode.end, loop=False)

    def _after_mode_end(self) -> None:
        self._mode_player.disconnect_finished()
        next_mode = self._pending_mode
        if next_mode is None:
            self._resume_current_mode()
            return
        self._start_mode(next_mode)
