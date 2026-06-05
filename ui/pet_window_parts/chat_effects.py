"""Safe execution bridge for chat-requested visual effects."""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Protocol

from core.chat.config import ChatConfig, load_chat_config
from core.chat.models import EffectKind, EffectRequest, VISUAL_STATES
from core.playback.catalog import AnimationCatalog
from core.playback.clip import Clip, Mode

_LOG = logging.getLogger(__name__)

PERFORMED = "performed"
UNSUPPORTED = "unsupported"
UNKNOWN = "unknown"
DISABLED = "disabled"
BUSY = "busy"
UNAVAILABLE_FOR_VISUAL_STATE = "unavailable_for_visual_state"
NO_CLIP = "no_clip"
EXECUTION_FAILED = "execution_failed"
INVALID_VISUAL_STATE = "invalid_visual_state"

_ALLOWED_ACTION_TYPES = {"single", "phased"}


class _Director(Protocol):
    def pet_state(self) -> str: ...
    def is_interaction_active(self) -> bool: ...
    def is_visual_override_active(self) -> bool: ...
    def is_mode_available(self, mode_name: str) -> bool: ...
    def start_interaction(self, interaction_name: str): ...
    def end_interaction(self) -> None: ...


class _SinglePlayer(Protocol):
    def is_active(self) -> bool: ...

    def play(
        self,
        clip: Clip,
        on_finished: Callable[[], None] | None = None,
        *,
        resume: bool = True,
        interruptible: bool = False,
    ) -> bool: ...


@dataclass(frozen=True, slots=True)
class ChatEffectExecutionResult:
    action_id: str | None
    reason: str


class ChatActionEffectExecutor:
    """Execute the tiny v1 chat action surface through existing playback APIs."""

    def __init__(
        self,
        *,
        director: _Director,
        animation_catalog: AnimationCatalog,
        action_blocked: Callable[[], bool],
        single_active: Callable[[], bool],
        automated_action_active: Callable[[], bool],
        auto_move_active: Callable[[], bool],
        schedule_once: Callable[[int, Callable[[], None]], None],
        config: ChatConfig | None = None,
        single_player: _SinglePlayer | None = None,
        allowed_action_ids: Sequence[str] | None = None,
    ) -> None:
        self._director = director
        self._animation_catalog = animation_catalog
        self._action_blocked = action_blocked
        self._single_active = single_active
        self._automated_action_active = automated_action_active
        self._auto_move_active = auto_move_active
        self._schedule_once = schedule_once
        self._config = config or load_chat_config()
        self._single_player = single_player
        self._allowed_action_ids = _allowed_action_ids(self._config, allowed_action_ids)
        self._last_results: tuple[ChatEffectExecutionResult, ...] = ()
        self._active_action_id: str | None = None
        self._active_token = 0

    @property
    def last_results(self) -> tuple[ChatEffectExecutionResult, ...]:
        return self._last_results

    def set_single_player(self, single_player: _SinglePlayer) -> None:
        self._single_player = single_player

    def execute(self, effects: Sequence[EffectRequest]) -> tuple[str, ...]:
        results = tuple(self._execute_safely(effect) for effect in effects)
        self._last_results = results
        for result in results:
            _LOG.debug("chat effect action_id=%s reason=%s", result.action_id, result.reason)
        return tuple(result.reason for result in results)

    def _execute_safely(self, effect: EffectRequest) -> ChatEffectExecutionResult:
        action_id = _clean_id(getattr(effect, "action_id", None))
        try:
            return self._execute_one(effect, action_id)
        except Exception:
            _LOG.exception("chat effect execution failed action_id=%s", action_id)
            return ChatEffectExecutionResult(action_id, EXECUTION_FAILED)

    def _execute_one(
        self,
        effect: EffectRequest,
        action_id: str | None,
    ) -> ChatEffectExecutionResult:
        if _effect_kind(effect) != EffectKind.ACTION:
            return ChatEffectExecutionResult(action_id, UNSUPPORTED)
        if action_id is None:
            return ChatEffectExecutionResult(None, UNKNOWN)

        action_spec = self._config.actions.get(action_id)
        if action_spec is None:
            return ChatEffectExecutionResult(action_id, UNKNOWN)
        if action_id not in self._allowed_action_ids or not _allow_in_v1(action_spec):
            return ChatEffectExecutionResult(action_id, DISABLED)

        visual_state = _clean_id(self._director.pet_state())
        if visual_state not in VISUAL_STATES:
            return ChatEffectExecutionResult(action_id, INVALID_VISUAL_STATE)

        if self._is_busy():
            return ChatEffectExecutionResult(action_id, BUSY)
        if not self._animation_catalog.has_action(action_id):
            return ChatEffectExecutionResult(action_id, NO_CLIP)
        if not self._has_explicit_state_material(action_id, visual_state) and not self._has_any_material(action_id):
            return ChatEffectExecutionResult(action_id, UNAVAILABLE_FOR_VISUAL_STATE)

        try:
            action_type = self._animation_catalog.action_type(action_id)
        except KeyError:
            return ChatEffectExecutionResult(action_id, NO_CLIP)
        if action_type not in _ALLOWED_ACTION_TYPES:
            return ChatEffectExecutionResult(action_id, NO_CLIP)
        if action_type == "single":
            return self._play_single_action(action_id, visual_state)
        return self._play_phased_action(action_id, visual_state)

    def _is_busy(self) -> bool:
        return (
            _call_bool(self._action_blocked)
            or _call_bool(self._single_active)
            or _call_bool(self._automated_action_active)
            or _call_bool(self._auto_move_active)
            or _call_bool(getattr(self._director, "is_visual_override_active", None))
            or _call_bool(getattr(self._director, "is_interaction_active", None))
            or self._single_player_is_active()
        )

    def _single_player_is_active(self) -> bool:
        if self._single_player is None:
            return False
        return _call_bool(getattr(self._single_player, "is_active", None))

    def _has_explicit_state_material(self, action_id: str, visual_state: str) -> bool:
        pet_states_for = getattr(self._animation_catalog, "pet_states_for", None)
        if callable(pet_states_for):
            return visual_state in pet_states_for(action_id)
        material_states_for = getattr(self._animation_catalog, "material_states_for", None)
        if callable(material_states_for):
            return visual_state in material_states_for(action_id)
        return True

    def _has_any_material(self, action_id: str) -> bool:
        has_material_fallback = getattr(self._animation_catalog, "has_material_fallback", None)
        if callable(has_material_fallback):
            return bool(has_material_fallback(action_id))
        material_states_for = getattr(self._animation_catalog, "material_states_for", None)
        if callable(material_states_for):
            return "any" in material_states_for(action_id)
        return False

    def _play_single_action(
        self,
        action_id: str,
        visual_state: str,
    ) -> ChatEffectExecutionResult:
        if self._single_player is None:
            return ChatEffectExecutionResult(action_id, NO_CLIP)
        if not self._animation_catalog.is_single_available(action_id, visual_state):
            return ChatEffectExecutionResult(action_id, NO_CLIP)
        clip = self._animation_catalog.single_for(action_id, visual_state)

        token = self._begin_action(action_id)
        if not self._single_player.play(
            clip,
            on_finished=lambda: self._clear_action(token),
            resume=True,
            interruptible=False,
        ):
            self._clear_action(token)
            return ChatEffectExecutionResult(action_id, EXECUTION_FAILED)
        return ChatEffectExecutionResult(action_id, PERFORMED)

    def _play_phased_action(
        self,
        action_id: str,
        visual_state: str,
    ) -> ChatEffectExecutionResult:
        if not self._animation_catalog.is_mode_available(
            action_id,
            visual_state,
            action_type="phased",
        ):
            return ChatEffectExecutionResult(action_id, NO_CLIP)
        token = self._begin_action(action_id)
        mode = self._director.start_interaction(action_id)
        if mode is None:
            self._clear_action(token)
            return ChatEffectExecutionResult(action_id, BUSY)
        self._schedule_once(
            _short_interaction_hold_ms(mode),
            lambda: self._end_phased_action_if_current(token, action_id),
        )
        return ChatEffectExecutionResult(action_id, PERFORMED)

    def _begin_action(self, action_id: str) -> int:
        self._active_token += 1
        self._active_action_id = action_id
        return self._active_token

    def _clear_action(self, token: int) -> None:
        if token != self._active_token:
            return
        self._active_action_id = None

    def _end_phased_action_if_current(self, token: int, action_id: str) -> None:
        if token != self._active_token or self._active_action_id != action_id:
            return
        try:
            if self._current_interaction_matches(action_id):
                self._director.end_interaction()
        except Exception:
            _LOG.debug("chat effect finish skipped action_id=%s", action_id, exc_info=True)
        finally:
            self._clear_action(token)

    def _current_interaction_matches(self, action_id: str) -> bool:
        snapshot_factory = getattr(self._director, "debug_snapshot", None)
        if not callable(snapshot_factory):
            return False
        snapshot = snapshot_factory()
        return (
            getattr(snapshot, "source", None) == "interaction"
            and getattr(snapshot, "action_id", None) == action_id
        )


def _allowed_action_ids(
    config: ChatConfig,
    allowed_action_ids: Sequence[str] | None,
) -> frozenset[str]:
    if allowed_action_ids is not None:
        return frozenset(_clean_id(action_id) or "" for action_id in allowed_action_ids)
    return frozenset(
        action_id
        for action_id, action in config.actions.items()
        if _allow_in_v1(action)
    )


def _allow_in_v1(action_spec) -> bool:
    if isinstance(action_spec, dict):
        return bool(action_spec.get("allow_in_v1", False))
    return bool(getattr(action_spec, "allow_in_v1", False))


def _effect_kind(effect: EffectRequest) -> EffectKind | None:
    try:
        return EffectKind(getattr(effect, "kind", None))
    except (TypeError, ValueError):
        return None


def _clean_id(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _call_bool(callback: Callable[[], bool] | None) -> bool:
    if not callable(callback):
        return False
    try:
        return bool(callback())
    except Exception:
        return True


def _short_interaction_hold_ms(mode: Mode) -> int:
    start = getattr(mode, "start", None)
    loop = getattr(mode, "loop", None)
    start_ms = int(getattr(start, "duration_ms", 0) or 0)
    loop_ms = int(getattr(loop, "duration_ms", 0) or 0)
    return max(1, start_ms + loop_ms)


__all__ = [
    "BUSY",
    "ChatActionEffectExecutor",
    "ChatEffectExecutionResult",
    "DISABLED",
    "EXECUTION_FAILED",
    "INVALID_VISUAL_STATE",
    "NO_CLIP",
    "PERFORMED",
    "UNAVAILABLE_FOR_VISUAL_STATE",
    "UNKNOWN",
    "UNSUPPORTED",
]
