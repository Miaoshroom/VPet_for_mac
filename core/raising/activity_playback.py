"""活动、照顾动画和真实状态到播放系统之间的轻量桥接。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from core.raising.activity import ActivityDefinition
from core.raising.pet_state import PetState, VisualPetState
from core.playback.clip import Clip, Mode
from core.playback.catalog import AnimationCatalog


class _Director(Protocol):
    def current_mode_name(self) -> str: ...
    def is_interaction_active(self) -> bool: ...
    def is_mode_available(self, mode_name: str) -> bool: ...
    def is_visual_override_active(self) -> bool: ...
    def mode_for_action(self, mode_name: str) -> Mode: ...
    def pet_state(self) -> str: ...
    def set_pet_state(self, pet_state: str, *, resume: bool = True) -> None: ...
    def start_default_mode(self) -> None: ...
    def start_interaction(self, interaction_name: str): ...
    def end_interaction(self) -> None: ...
    def stop_active_interaction(self, *, resume: bool = True) -> bool: ...
    def switch_mode(self, mode_name: str) -> None: ...


class _SinglePlayer(Protocol):
    def play(
        self,
        clip: Clip,
        on_finished: Callable[[], None] | None = None,
        *,
        resume: bool = True,
        interruptible: bool = False,
    ) -> bool: ...


@dataclass(frozen=True, slots=True)
class PlaybackStartCheck:
    ok: bool
    message: str = ""


@dataclass(frozen=True, slots=True)
class ActivityPlaybackResult:
    started: bool
    action_id: str | None
    message: str = ""


@dataclass(frozen=True, slots=True)
class VisualStateResult:
    suggested_state: VisualPetState
    current_state: str
    applied: bool
    pending: bool
    message: str = ""


@dataclass(frozen=True, slots=True)
class CareAnimationSpec:
    care_action_id: str
    action_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CarePlaybackResult:
    started: bool
    action_id: str | None
    message: str = ""


CARE_ANIMATION_SPECS: dict[str, CareAnimationSpec] = {
    "simple_feed": CareAnimationSpec(
        care_action_id="simple_feed",
        action_ids=("eat",),
    ),
    "drink": CareAnimationSpec(
        care_action_id="drink",
        action_ids=("drink", "switch_thirsty"),
    ),
    "simple_clean": CareAnimationSpec(
        care_action_id="simple_clean",
        action_ids=("work_clean",),
    ),
    "medicine": CareAnimationSpec(
        care_action_id="medicine",
        action_ids=("eat",),
    ),
    "gift": CareAnimationSpec(
        care_action_id="gift",
        action_ids=("gift",),
    ),
}


class ActivityPlaybackBridge:
    """把活动定义里的动画请求安全转成 director 播放请求。"""

    def __init__(
        self,
        director: _Director,
        animation_catalog: AnimationCatalog,
        *,
        action_blocked: Callable[[], bool],
        single_active: Callable[[], bool],
    ) -> None:
        self._director = director
        self._animation_catalog = animation_catalog
        self._action_blocked = action_blocked
        self._single_active = single_active
        self._active_activity_id: str | None = None
        self._active_action_id: str | None = None
        self._active_kind: str | None = None
        self._resume_mode: str | None = None

    def can_start_activity(self) -> PlaybackStartCheck:
        if self._action_blocked():
            return PlaybackStartCheck(False, "插件动作占用中，稍后再开始活动。")
        if self._single_active() or self._director.is_visual_override_active():
            return PlaybackStartCheck(False, "当前动作占用中，稍后再开始活动。")
        if self._director.is_interaction_active():
            return PlaybackStartCheck(False, "当前互动动作占用中，稍后再开始活动。")
        return PlaybackStartCheck(True)

    def is_active(self) -> bool:
        return self._active_action_id is not None

    def start_activity_animation(self, activity: ActivityDefinition) -> ActivityPlaybackResult:
        if self.is_active():
            return ActivityPlaybackResult(
                started=False,
                action_id=self._active_action_id,
                message="已有活动动画进行中。",
            )
        check = self.can_start_activity()
        if not check.ok:
            return ActivityPlaybackResult(
                started=False,
                action_id=None,
                message=check.message,
            )

        configured_ids = activity.animation_action_ids()
        if not configured_ids:
            return ActivityPlaybackResult(started=False, action_id=None)

        action_id, action_type = self._pick_playable_action(configured_ids)
        if action_id is None or action_type is None:
            return ActivityPlaybackResult(
                started=False,
                action_id=None,
                message="已开始数值活动，但当前表现状态没有可用活动动画。",
            )

        self._active_activity_id = activity.id
        self._active_action_id = action_id
        self._active_kind = "interaction" if action_type == "phased" else "mode"
        self._resume_mode = self._director.current_mode_name()

        try:
            if action_type == "phased":
                mode = self._director.start_interaction(action_id)
                if mode is None:
                    self._clear_active()
                    return ActivityPlaybackResult(
                        started=False,
                        action_id=action_id,
                        message="已开始数值活动，但活动动画暂时无法播放。",
                    )
            else:
                self._director.switch_mode(action_id)
        except (KeyError, ValueError):
            self._clear_active()
            return ActivityPlaybackResult(
                started=False,
                action_id=action_id,
                message="已开始数值活动，但活动动画素材不可用。",
            )

        return ActivityPlaybackResult(started=True, action_id=action_id)

    def finish_activity_animation(self) -> ActivityPlaybackResult:
        action_id = self._active_action_id
        kind = self._active_kind
        resume_mode = self._resume_mode
        self._clear_active()
        if action_id is None:
            return ActivityPlaybackResult(started=False, action_id=None)

        if kind == "interaction":
            self._director.end_interaction()
            return ActivityPlaybackResult(started=False, action_id=action_id)

        try:
            if resume_mode is not None and self._director.is_mode_available(resume_mode):
                self._director.switch_mode(resume_mode)
            else:
                self._director.start_default_mode()
        except (KeyError, ValueError):
            self._director.start_default_mode()
        return ActivityPlaybackResult(started=False, action_id=action_id)

    def suspend_activity_animation(self) -> ActivityPlaybackResult:
        action_id = self._active_action_id
        if action_id is None:
            return ActivityPlaybackResult(started=False, action_id=None)
        if self._active_kind != "interaction":
            return ActivityPlaybackResult(started=False, action_id=action_id)
        self._clear_active()
        self._director.stop_active_interaction(resume=False)
        return ActivityPlaybackResult(started=False, action_id=action_id)

    def _pick_playable_action(
        self,
        action_ids: tuple[str, ...],
    ) -> tuple[str | None, str | None]:
        for action_id in action_ids:
            if not self._animation_catalog.has_action(action_id):
                continue
            try:
                action_type = self._animation_catalog.action_type(action_id)
            except KeyError:
                continue
            if action_type not in {"loop", "phased"}:
                continue
            if not self._director.is_mode_available(action_id):
                continue
            return action_id, action_type
        return None, None

    def _clear_active(self) -> None:
        self._active_activity_id = None
        self._active_action_id = None
        self._active_kind = None
        self._resume_mode = None


class CarePlaybackBridge:
    """把物品使用和自动补状态的照顾动画请求安全转成播放请求。"""

    def __init__(
        self,
        director: _Director,
        animation_catalog: AnimationCatalog,
        *,
        action_blocked: Callable[[], bool],
        activity_active: Callable[[], bool],
        single_active: Callable[[], bool],
        schedule_once: Callable[[int, Callable[[], None]], None],
        on_finished: Callable[[], None] | None = None,
    ) -> None:
        self._director = director
        self._animation_catalog = animation_catalog
        self._action_blocked = action_blocked
        self._activity_active = activity_active
        self._single_active = single_active
        self._schedule_once = schedule_once
        self._on_finished = on_finished or (lambda: None)
        self._single_player: _SinglePlayer | None = None
        self._active_care_action_id: str | None = None
        self._active_action_id: str | None = None
        self._active_kind: str | None = None
        self._resume_mode: str | None = None
        self._generation = 0

    def set_single_player(self, single_player: _SinglePlayer) -> None:
        self._single_player = single_player

    def animation_candidates(self, care_action_id: str) -> tuple[str, ...]:
        spec = CARE_ANIMATION_SPECS.get(care_action_id)
        if spec is None:
            return ()
        return spec.action_ids

    def can_start_care(self) -> PlaybackStartCheck:
        if self._action_blocked():
            return PlaybackStartCheck(False, "插件动作占用中，稍后再照顾。")
        if self._activity_active():
            return PlaybackStartCheck(False, "活动进行中，稍后再照顾。")
        if (
            self._single_active()
            or self._director.is_visual_override_active()
            or self._director.is_interaction_active()
            or self.is_active()
        ):
            return PlaybackStartCheck(False, "当前动作占用中，稍后再照顾。")
        return PlaybackStartCheck(True)

    def is_active(self) -> bool:
        return self._active_action_id is not None

    def start_care_animation(self, care_action_id: str) -> CarePlaybackResult:
        if self.is_active():
            return CarePlaybackResult(
                started=False,
                action_id=self._active_action_id,
                message="已有照顾动画进行中。",
            )

        action_id, action_type = self._pick_playable_action(
            self.animation_candidates(care_action_id)
        )
        if action_id is None or action_type is None:
            return CarePlaybackResult(
                started=False,
                action_id=None,
                message="照顾成功，但当前表现状态没有可用照顾动画。",
            )

        self._active_care_action_id = care_action_id
        self._active_action_id = action_id
        self._active_kind = action_type
        self._resume_mode = self._director.current_mode_name()
        self._generation += 1
        generation = self._generation

        try:
            if action_type == "single":
                result = self._start_single_action(action_id)
            elif action_type == "phased":
                result = self._start_phased_action(action_id, generation)
            else:
                result = self._start_loop_action(action_id, generation)
        except (KeyError, ValueError):
            self._clear_active()
            return CarePlaybackResult(
                started=False,
                action_id=action_id,
                message="照顾成功，但照顾动画素材不可用。",
            )

        if not result.started:
            self._clear_active()
        return result

    def request_finish(self) -> CarePlaybackResult:
        action_id = self._active_action_id
        kind = self._active_kind
        if action_id is None:
            return CarePlaybackResult(started=False, action_id=None)
        if kind == "phased":
            self._director.end_interaction()
            return CarePlaybackResult(started=False, action_id=action_id)
        return self._finish_now()

    def on_playback_idle(self) -> CarePlaybackResult:
        if self._active_kind != "phased":
            return CarePlaybackResult(started=False, action_id=self._active_action_id)
        return self._finish_now()

    def _start_single_action(self, action_id: str) -> CarePlaybackResult:
        if self._single_player is None:
            return CarePlaybackResult(
                started=False,
                action_id=action_id,
                message="照顾成功，但当前没有可用的 single 播放器。",
            )
        clip = self._animation_catalog.single_for(action_id, self._director.pet_state())
        if not self._single_player.play(
            clip,
            on_finished=lambda: self._finish_now(),
            resume=True,
            interruptible=False,
        ):
            return CarePlaybackResult(
                started=False,
                action_id=action_id,
                message="照顾成功，但照顾动画暂时无法播放。",
            )
        return CarePlaybackResult(started=True, action_id=action_id)

    def _start_phased_action(self, action_id: str, generation: int) -> CarePlaybackResult:
        mode = self._director.start_interaction(action_id)
        if mode is None:
            return CarePlaybackResult(
                started=False,
                action_id=action_id,
                message="照顾成功，但照顾动画暂时无法播放。",
            )
        hold_ms = _care_interaction_hold_ms(mode)
        self._schedule_once(hold_ms, lambda: self._request_finish_if_current(generation))
        return CarePlaybackResult(started=True, action_id=action_id)

    def _start_loop_action(self, action_id: str, generation: int) -> CarePlaybackResult:
        mode = self._director.mode_for_action(action_id)
        self._director.switch_mode(action_id)
        hold_ms = max(1, mode.loop.duration_ms)
        self._schedule_once(hold_ms, lambda: self._request_finish_if_current(generation))
        return CarePlaybackResult(started=True, action_id=action_id)

    def _request_finish_if_current(self, generation: int) -> None:
        if generation != self._generation or self._active_action_id is None:
            return
        self.request_finish()

    def _finish_now(self) -> CarePlaybackResult:
        action_id = self._active_action_id
        kind = self._active_kind
        resume_mode = self._resume_mode
        self._clear_active()
        if action_id is None:
            return CarePlaybackResult(started=False, action_id=None)
        if kind == "loop":
            self._restore_resume_mode(resume_mode)
        self._on_finished()
        return CarePlaybackResult(started=False, action_id=action_id)

    def _restore_resume_mode(self, resume_mode: str | None) -> None:
        try:
            if resume_mode is not None and self._director.is_mode_available(resume_mode):
                self._director.switch_mode(resume_mode)
            else:
                self._director.start_default_mode()
        except (KeyError, ValueError):
            self._director.start_default_mode()

    def _pick_playable_action(
        self,
        action_ids: tuple[str, ...],
    ) -> tuple[str | None, str | None]:
        for action_id in action_ids:
            if not self._animation_catalog.has_action(action_id):
                continue
            try:
                action_type = self._animation_catalog.action_type(action_id)
            except KeyError:
                continue
            if action_type == "single":
                if self._animation_catalog.is_single_available(
                    action_id,
                    self._director.pet_state(),
                ):
                    return action_id, action_type
                continue
            if action_type not in {"loop", "phased"}:
                continue
            if not self._director.is_mode_available(action_id):
                continue
            return action_id, action_type
        return None, None

    def _clear_active(self) -> None:
        self._active_care_action_id = None
        self._active_action_id = None
        self._active_kind = None
        self._resume_mode = None


class VisualStateBridge:
    """把 PetState.suggested_visual_state() 延迟、安全地应用到 director。"""

    def __init__(
        self,
        pet_state: PetState,
        director: _Director,
        *,
        action_blocked: Callable[[], bool],
        single_active: Callable[[], bool],
        activity_animation_active: Callable[[], bool],
        care_animation_active: Callable[[], bool] | None = None,
    ) -> None:
        self._pet_state = pet_state
        self._director = director
        self._action_blocked = action_blocked
        self._single_active = single_active
        self._activity_animation_active = activity_animation_active
        self._care_animation_active = care_animation_active or (lambda: False)
        self._pending_state: VisualPetState | None = None

    def pending_state(self) -> VisualPetState | None:
        return self._pending_state

    def request_update(self) -> VisualStateResult:
        suggested = self._pet_state.suggested_visual_state()
        current = self._director.pet_state()
        if suggested == current:
            self._pending_state = None
            return VisualStateResult(
                suggested_state=suggested,
                current_state=current,
                applied=False,
                pending=False,
            )
        if not self._can_apply_now():
            self._pending_state = suggested
            return VisualStateResult(
                suggested_state=suggested,
                current_state=current,
                applied=False,
                pending=True,
                message="表现状态已等待空闲后应用。",
            )
        return self._apply(suggested)

    def apply_pending_if_possible(self) -> VisualStateResult:
        if self._pending_state is None:
            return self.request_update()
        if not self._can_apply_now():
            return VisualStateResult(
                suggested_state=self._pending_state,
                current_state=self._director.pet_state(),
                applied=False,
                pending=True,
                message="表现状态仍在等待空闲。",
            )
        return self.request_update()

    def _apply(self, visual_state: VisualPetState) -> VisualStateResult:
        try:
            self._director.set_pet_state(visual_state, resume=True)
        except (KeyError, ValueError) as exc:
            self._pending_state = visual_state
            return VisualStateResult(
                suggested_state=visual_state,
                current_state=self._director.pet_state(),
                applied=False,
                pending=True,
                message=f"表现状态暂时不可用：{exc}",
            )
        self._pending_state = None
        return VisualStateResult(
            suggested_state=visual_state,
            current_state=self._director.pet_state(),
            applied=True,
            pending=False,
        )

    def _can_apply_now(self) -> bool:
        return not (
            self._action_blocked()
            or self._single_active()
            or self._director.is_visual_override_active()
            or self._director.is_interaction_active()
            or self._activity_animation_active()
            or self._care_animation_active()
        )


def _care_interaction_hold_ms(mode: Mode) -> int:
    start_ms = mode.start.duration_ms if mode.start is not None else 0
    return max(1, start_ms + mode.loop.duration_ms)


__all__ = [
    "ActivityPlaybackBridge",
    "ActivityPlaybackResult",
    "CARE_ANIMATION_SPECS",
    "CareAnimationSpec",
    "CarePlaybackBridge",
    "CarePlaybackResult",
    "PlaybackStartCheck",
    "VisualStateBridge",
    "VisualStateResult",
]
