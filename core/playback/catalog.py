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
LAYER_DRAW_ORDER = ("back", "main", "front")
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

    def available_action_ids(
        self,
        pet_state: str,
        action_type: ActionType | None = None,
    ) -> tuple[str, ...]:
        # 统一从这里问当前状态能播哪些动作
        pet_state = validate_pet_state(pet_state)
        result: list[str] = []
        for action_id in self.action_ids(action_type):
            if self.is_action_available(action_id, pet_state, action_type=action_type):
                result.append(action_id)
        return tuple(result)

    def is_action_available(
        self,
        action_id: str,
        pet_state: str,
        *,
        action_type: ActionType | None = None,
    ) -> bool:
        # 可播不是只看目录存在 还要能拿到 main 图层
        mode_type = action_type or self.action_type(action_id)
        if mode_type == "single":
            return self.is_single_available(action_id, pet_state)
        return self.is_mode_available(action_id, pet_state, action_type=mode_type)

    def is_mode_available(
        self,
        action_id: str,
        pet_state: str,
        *,
        action_type: ActionType | None = None,
    ) -> bool:
        pet_state = validate_pet_state(pet_state)
        mode_type = action_type or self.action_type(action_id)
        if mode_type == "single":
            return False
        try:
            _, state_data = self._state_data(action_id, pet_state)
        except KeyError:
            return False
        if mode_type == "loop":
            return bool(self._playable_variants(state_data, "loop"))
        if mode_type == "phased":
            return bool(self._playable_phased_loop_variants(state_data))
        return False

    def is_single_available(self, action_id: str, pet_state: str) -> bool:
        pet_state = validate_pet_state(pet_state)
        try:
            _, state_data = self._state_data(action_id, pet_state)
        except KeyError:
            return False
        return bool(self._playable_variants(state_data, "single"))

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
            loop = self._clip_for_variant(
                state_data,
                "loop",
                variant,
                action_id=action_id,
                source_state=state_name,
            )
            return Mode(
                loop=loop,
                action_id=action_id,
                source_state=state_name,
                loop_variant=variant,
            )
        if mode_type != "phased":
            raise KeyError(f"未知动作类型: {mode_type}")
        loop_selected = self._pick_phased_loop_variant(state_data, loop_variant)
        start_selected = self._phase_variant_or_default(state_data, "start", loop_selected)
        end_selected = self._phase_variant_or_default(state_data, "end", loop_selected)
        return Mode(
            loop=self._clip_for_variant(
                state_data,
                "loop",
                loop_selected,
                action_id=action_id,
                source_state=state_name,
            ),
            start=self._clip_for_variant(
                state_data,
                "start",
                start_selected,
                action_id=action_id,
                source_state=state_name,
            ),
            end=self._clip_for_variant(
                state_data,
                "end",
                end_selected,
                action_id=action_id,
                source_state=state_name,
            ),
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
        state_name, state_data = self._state_data(action_id, pet_state)
        selected = self._pick_variant(state_data, "single", variant)
        return self._clip_for_variant(
            state_data,
            "single",
            selected,
            action_id=action_id,
            source_state=state_name,
        )

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

    def _action_data(self, action_id: str) -> StateClips:
        try:
            return self._clips[action_id]
        except KeyError as exc:
            raise KeyError(f"未知动作: {action_id}") from exc

    def _state_data(self, action_id: str, pet_state: str) -> tuple[str, PhaseClips]:
        action_data = self._action_data(action_id)
        if pet_state in action_data:
            if "any" in action_data:
                return pet_state, self._merge_state_data(action_data["any"], action_data[pet_state])
            return pet_state, action_data[pet_state]
        if "any" in action_data:
            return "any", action_data["any"]
        raise KeyError(f"动作 {action_id} 没有 {pet_state} 状态素材，也没有 any 兜底")

    def _merge_state_data(self, fallback: PhaseClips, exact: PhaseClips) -> PhaseClips:
        merged: PhaseClips = {
            phase: {
                variant: dict(layers)
                for variant, layers in variants.items()
            }
            for phase, variants in fallback.items()
        }
        for phase, variants in exact.items():
            phase_data = merged.setdefault(phase, {})
            for variant, layers in variants.items():
                layer_data = phase_data.setdefault(variant, {})
                layer_data.update(layers)
        return merged

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
        variants = self._playable_variants(state_data, phase)
        if not variants:
            raise KeyError(f"阶段 {phase} 没有可播放图层")
        if requested is not None:
            if requested not in variants:
                raise KeyError(f"阶段 {phase} 不存在变体 {requested}")
            return requested
        return random.choice(variants)

    def _pick_phased_loop_variant(
        self,
        state_data: PhaseClips,
        requested: str | None,
    ) -> str:
        variants = self._playable_phased_loop_variants(state_data)
        if not variants:
            raise KeyError("phased 动画没有完整可播放的 start-loop-end")
        if requested is not None:
            if requested not in variants:
                raise KeyError(f"phased 动画变体 {requested} 缺少 start 或 end")
            return requested
        return random.choice(variants)

    def _playable_phased_loop_variants(self, state_data: PhaseClips) -> tuple[str, ...]:
        # phased 必须先确认 start loop end 能凑成一套
        result: list[str] = []
        for loop_variant in self._playable_variants(state_data, "loop"):
            if (
                self._phase_variant_available(state_data, "start", loop_variant)
                and self._phase_variant_available(state_data, "end", loop_variant)
            ):
                result.append(loop_variant)
        return tuple(result)

    def _phase_variant_available(
        self,
        state_data: PhaseClips,
        phase: str,
        loop_variant: str,
    ) -> bool:
        phase_variants = state_data.get(phase, {})
        if loop_variant in phase_variants and self._has_playable_layer(phase_variants[loop_variant]):
            return True
        return "01" in phase_variants and self._has_playable_layer(phase_variants["01"])

    def _playable_variants(self, state_data: PhaseClips, phase: str) -> tuple[str, ...]:
        return tuple(
            sorted(
                variant
                for variant, layers in state_data.get(phase, {}).items()
                if self._has_playable_layer(layers)
            )
        )

    def _has_playable_layer(self, layers: LayerClips) -> bool:
        return any(layer in layers for layer in LAYER_DRAW_ORDER)

    def _phase_variant_or_default(
        self,
        state_data: PhaseClips,
        phase: str,
        loop_variant: str,
    ) -> str:
        phase_variants = state_data.get(phase, {})
        if loop_variant in phase_variants and self._has_playable_layer(phase_variants[loop_variant]):
            return loop_variant
        if "01" in phase_variants and self._has_playable_layer(phase_variants["01"]):
            return "01"
        raise KeyError(f"phased 动画缺少 {phase}/{loop_variant}，且没有 {phase}/01 可回退")

    def _clip_for_variant(
        self,
        state_data: PhaseClips,
        phase: str,
        variant: str,
        *,
        action_id: str | None = None,
        source_state: str | None = None,
    ) -> Clip:
        try:
            layers = state_data[phase][variant]
        except KeyError as exc:
            raise KeyError(f"阶段 {phase}/{variant} 不存在") from exc
        playable_layers = tuple(
            (layer, layers[layer])
            for layer in LAYER_DRAW_ORDER
            if layer in layers
        )
        if not playable_layers:
            raise KeyError(f"阶段 {phase}/{variant} 没有可播放图层")
        if len(playable_layers) == 1:
            clip = playable_layers[0][1]
        else:
            clip = Clip.from_layer_clips(dict(playable_layers), LAYER_DRAW_ORDER)
        if action_id is None or source_state is None:
            return clip
        return clip.with_debug_metadata(
            action_id=action_id,
            source_state=source_state,
            phase=phase,
            variant=variant,
        )
