"""经验升级规则。

这里的 exp 采用扣除式：升级时消耗当前等级所需经验，剩余 exp 留给下一等级。
"""

from __future__ import annotations

from dataclasses import dataclass

from core.raising.pet_state import PetState

BASE_LEVEL_EXP = 40
LEVEL_EXP_STEP = 20
MIN_LEVEL = 1

LEVEL_REWARD_MONEY = 10
LEVEL_REWARD_AFFECTION = 1
LEVEL_REWARD_MOOD = 3
LEVEL_REWARD_ENERGY = 2
LEVEL_REWARD_HEALTH = 1


@dataclass(frozen=True, slots=True)
class LevelUpResult:
    leveled: bool
    old_level: int
    new_level: int
    levels_gained: int
    exp_before: int
    exp_after: int
    consumed_exp: int
    next_level_exp: int
    exp_to_next: int
    rewards: dict[str, int]


def required_exp_for_level(level: int) -> int:
    """返回从当前 level 升到下一等级所需的经验。"""

    level = max(MIN_LEVEL, int(level))
    return BASE_LEVEL_EXP + (level - MIN_LEVEL) * LEVEL_EXP_STEP


def exp_to_next_level(state: PetState) -> int:
    return max(0, required_exp_for_level(state.level) - int(state.exp))


def add_exp_and_apply_level_ups(state: PetState, amount: int) -> LevelUpResult:
    """给任意未来入口复用：先增加经验，再按同一规则升级。"""

    if amount > 0:
        state.exp = max(0, int(state.exp) + int(amount))
    return apply_level_ups(state)


def apply_level_ups(state: PetState) -> LevelUpResult:
    """检查并结算升级，支持一次获得经验后连升多级。"""

    state.level = max(MIN_LEVEL, int(state.level))
    state.exp = max(0, int(state.exp))
    old_level = state.level
    exp_before = state.exp
    consumed_exp = 0
    levels_gained = 0

    while state.exp >= required_exp_for_level(state.level):
        required = required_exp_for_level(state.level)
        state.exp -= required
        consumed_exp += required
        state.level += 1
        levels_gained += 1

    rewards: dict[str, int] = {}
    if levels_gained:
        rewards = _apply_level_rewards(state, levels_gained)

    next_level_exp = required_exp_for_level(state.level)
    return LevelUpResult(
        leveled=levels_gained > 0,
        old_level=old_level,
        new_level=state.level,
        levels_gained=levels_gained,
        exp_before=exp_before,
        exp_after=state.exp,
        consumed_exp=consumed_exp,
        next_level_exp=next_level_exp,
        exp_to_next=max(0, next_level_exp - state.exp),
        rewards=rewards,
    )


def format_level_up_notice(result: LevelUpResult) -> str:
    if not result.leveled:
        return ""
    if result.levels_gained == 1:
        prefix = f"升级到 Lv.{result.new_level}！"
    else:
        prefix = f"连升 {result.levels_gained} 级到 Lv.{result.new_level}！"
    reward_text = _format_rewards(result.rewards)
    return prefix if not reward_text else f"{prefix}奖励：{reward_text}"


def _apply_level_rewards(state: PetState, levels_gained: int) -> dict[str, int]:
    planned_rewards = {
        "money": LEVEL_REWARD_MONEY * levels_gained,
        "affection": LEVEL_REWARD_AFFECTION * levels_gained,
        "mood": LEVEL_REWARD_MOOD * levels_gained,
        "energy": LEVEL_REWARD_ENERGY * levels_gained,
        "health": LEVEL_REWARD_HEALTH * levels_gained,
    }
    actual_rewards: dict[str, int] = {}
    for field, amount in planned_rewards.items():
        old_value = int(getattr(state, field))
        if field in {"mood", "energy", "health"}:
            new_value = _clamp_percent(old_value + amount)
        else:
            new_value = max(0, old_value + amount)
        if new_value == old_value:
            continue
        setattr(state, field, new_value)
        actual_rewards[field] = new_value - old_value
    return actual_rewards


def _format_rewards(rewards: dict[str, int]) -> str:
    labels = {
        "money": "金币",
        "affection": "亲密度",
        "mood": "心情",
        "energy": "体力",
        "health": "健康",
    }
    parts = [
        f"{labels.get(field, field)} +{amount}"
        for field, amount in rewards.items()
        if amount > 0
    ]
    return "、".join(parts)


def _clamp_percent(value: int) -> int:
    return min(100, max(0, int(value)))


__all__ = [
    "BASE_LEVEL_EXP",
    "LEVEL_EXP_STEP",
    "LevelUpResult",
    "add_exp_and_apply_level_ups",
    "apply_level_ups",
    "exp_to_next_level",
    "format_level_up_notice",
    "required_exp_for_level",
]
