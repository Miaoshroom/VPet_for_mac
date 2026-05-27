"""新 assets/animations 结构的动作目录"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass
from typing import Literal

from core.playback.clip import Clip, Mode

PET_STATES = ("happy", "normal", "poor_condition", "ill")
MATERIAL_STATES = PET_STATES + ("any",)
PHASES = ("loop", "start", "end", "single")
LAYERS = ("main", "back", "front")
MAIN_LAYER = "main"
DEFAULT_PET_STATE = "normal"

ActionType = Literal["loop", "phased", "single"]
LayerClips = dict[str, Clip]
VariantClips = dict[str, LayerClips]
PhaseClips = dict[str, VariantClips]
StateClips = dict[str, PhaseClips]
CatalogClips = dict[str, StateClips]

_VARIANT_RE = re.compile(r"^\d{2}$")


@dataclass(frozen=True)
class ActionSpec:
    id: str
    title: str
    type: ActionType


def is_valid_variant_name(name: str) -> bool:
    return _VARIANT_RE.fullmatch(name) is not None


def validate_pet_state(state: str) -> str:
    state = str(state)
    if state not in PET_STATES:
        raise ValueError(
            f"桌宠表现状态不合法: {state}。只允许 happy、normal、poor_condition、ill"
        )
    return state


class AnimationCatalog:
    """按动作 id 和桌宠表现状态查询动画片段"""

    def __init__(
        self,
        clips: CatalogClips,
        action_specs: dict[str, ActionSpec] | None = None,
    ) -> None:
        if not clips:
            raise ValueError("AnimationCatalog 至少需要一个动作")
        self._clips = clips
        self._action_specs = action_specs or {}

    def action_ids(self, action_type: ActionType | None = None) -> tuple[str, ...]:
        if action_type is None:
            return tuple(sorted(self._clips))
        return tuple(
            action_id
            for action_id in sorted(self._clips)
            if self.action_type(action_id) == action_type
        )

    def action_title(self, action_id: str) -> str:
        spec = self._action_specs.get(action_id)
        return spec.title if spec is not None else action_id

    def action_type(self, action_id: str) -> ActionType:
        spec = self._action_specs.get(action_id)
        if spec is not None:
            return spec.type
        phases = self._all_phases(action_id)
        if {"start", "loop", "end"} <= phases:
            return "phased"
        if "single" in phases and "loop" not in phases:
            return "single"
        if "loop" in phases:
            return "loop"
        raise KeyError(f"动作没有可播放阶段: {action_id}")

    def has_action(self, action_id: str) -> bool:
        return action_id in self._clips

    def material_states_for(self, action_id: str) -> tuple[str, ...]:
        return tuple(sorted(self._action_data(action_id)))

    def phases_for(self, action_id: str) -> tuple[str, ...]:
        return tuple(sorted(self._all_phases(action_id)))

    def pet_states_for(self, action_id: str) -> tuple[str, ...]:
        return tuple(state for state in PET_STATES if state in self._action_data(action_id))

    def has_material_fallback(self, action_id: str) -> bool:
        return "any" in self._action_data(action_id)

    def mode_for(
        self,
        action_id: str,
        pet_state: str,
        *,
        action_type: ActionType | None = None,
        loop_variant: str | None = None,
    ) -> Mode:
        pet_state = validate_pet_state(pet_state)
        mode_type = action_type or self.action_type(action_id)
        if mode_type == "single":
            raise KeyError(f"single 动作不能构造 Mode: {action_id}")
        state_name, state_data = self._state_data(action_id, pet_state)
        if mode_type == "loop":
            variant = self._pick_variant(state_data, "loop", loop_variant)
            loop = self._clip_for_variant(state_data, "loop", variant)
            return Mode(
                loop=loop,
                action_id=action_id,
                source_state=state_name,
                loop_variant=variant,
            )
        if mode_type != "phased":
            raise KeyError(f"未知动作类型: {mode_type}")
        loop_selected = self._pick_variant(state_data, "loop", loop_variant)
        start_selected = self._phase_variant_or_default(state_data, "start", loop_selected)
        end_selected = self._phase_variant_or_default(state_data, "end", loop_selected)
        return Mode(
            loop=self._clip_for_variant(state_data, "loop", loop_selected),
            start=self._clip_for_variant(state_data, "start", start_selected),
            end=self._clip_for_variant(state_data, "end", end_selected),
            action_id=action_id,
            source_state=state_name,
            loop_variant=loop_selected,
            start_variant=start_selected,
            end_variant=end_selected,
        )

    def single_for(
        self,
        action_id: str,
        pet_state: str,
        *,
        variant: str | None = None,
    ) -> Clip:
        pet_state = validate_pet_state(pet_state)
        _, state_data = self._state_data(action_id, pet_state)
        selected = self._pick_variant(state_data, "single", variant)
        return self._clip_for_variant(state_data, "single", selected)

    def variants_for(
        self,
        action_id: str,
        pet_state: str,
        phase: str,
        *,
        layer: str = MAIN_LAYER,
    ) -> tuple[str, ...]:
        pet_state = validate_pet_state(pet_state)
        if phase not in PHASES:
            raise KeyError(f"阶段不合法: {phase}")
        _, state_data = self._state_data(action_id, pet_state)
        variants = state_data.get(phase, {})
        return tuple(sorted(variant for variant, layers in variants.items() if layer in layers))

    def build_modes(
        self,
        action_specs: tuple[ActionSpec, ...],
        pet_state: str = DEFAULT_PET_STATE,
    ) -> dict[str, Mode]:
        modes: dict[str, Mode] = {}
        for spec in action_specs:
            if spec.type in ("loop", "phased"):
                try:
                    modes[spec.id] = self.mode_for(spec.id, pet_state, action_type=spec.type)
                except KeyError:
                    # 迁移期兼容字段只暴露当前状态可用的动作
                    pass
        return modes

    def build_single_clips(
        self,
        action_specs: tuple[ActionSpec, ...],
        pet_state: str = DEFAULT_PET_STATE,
    ) -> dict[str, Clip]:
        clips: dict[str, Clip] = {}
        for spec in action_specs:
            if spec.type == "single":
                try:
                    clips[spec.id] = self.single_for(spec.id, pet_state)
                except KeyError:
                    # 迁移期兼容字段只暴露当前状态可用的动作
                    pass
        return clips

    def _action_data(self, action_id: str) -> StateClips:
        try:
            return self._clips[action_id]
        except KeyError as exc:
            raise KeyError(f"未知动作: {action_id}") from exc

    def _state_data(self, action_id: str, pet_state: str) -> tuple[str, PhaseClips]:
        action_data = self._action_data(action_id)
        if pet_state in action_data:
            return pet_state, action_data[pet_state]
        if "any" in action_data:
            return "any", action_data["any"]
        raise KeyError(f"动作 {action_id} 没有 {pet_state} 状态素材，也没有 any 兜底")

    def _all_phases(self, action_id: str) -> set[str]:
        phases: set[str] = set()
        for state_data in self._action_data(action_id).values():
            phases.update(state_data)
        return phases

    def _pick_variant(
        self,
        state_data: PhaseClips,
        phase: str,
        requested: str | None,
    ) -> str:
        variants = tuple(
            sorted(
                variant
                for variant, layers in state_data.get(phase, {}).items()
                if MAIN_LAYER in layers
            )
        )
        if not variants:
            raise KeyError(f"阶段 {phase} 没有可播放 main 图层")
        if requested is not None:
            if requested not in variants:
                raise KeyError(f"阶段 {phase} 不存在变体 {requested}")
            return requested
        return random.choice(variants)

    def _phase_variant_or_default(
        self,
        state_data: PhaseClips,
        phase: str,
        loop_variant: str,
    ) -> str:
        phase_variants = state_data.get(phase, {})
        if loop_variant in phase_variants and MAIN_LAYER in phase_variants[loop_variant]:
            return loop_variant
        if "01" in phase_variants and MAIN_LAYER in phase_variants["01"]:
            return "01"
        raise KeyError(f"phased 动画缺少 {phase}/{loop_variant}，且没有 {phase}/01 可回退")

    def _clip_for_variant(self, state_data: PhaseClips, phase: str, variant: str) -> Clip:
        try:
            return state_data[phase][variant][MAIN_LAYER]
        except KeyError as exc:
            raise KeyError(f"阶段 {phase}/{variant} 没有可播放 main 图层") from exc
