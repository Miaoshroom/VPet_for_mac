"""自动补状态的最小选物策略。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from core.raising.items import ItemCatalog, ItemCategory, ItemDefinition, item_count
from core.raising.pet_state import PetState

AutoRefillField = Literal["satiety", "energy", "health", "cleanliness"]
AutoRefillDecisionKind = Literal["not_triggered", "selected", "missing_stock"]
AutoPurchaseDecisionKind = Literal["not_found", "selected", "insufficient_money"]


@dataclass(frozen=True, slots=True)
class AutoRefillRule:
    field: AutoRefillField
    threshold: int
    category: ItemCategory


@dataclass(frozen=True, slots=True)
class AutoRefillSelection:
    rule: AutoRefillRule
    item: ItemDefinition
    current_value: int


@dataclass(frozen=True, slots=True)
class AutoRefillDecision:
    kind: AutoRefillDecisionKind
    rule: AutoRefillRule | None = None
    item: ItemDefinition | None = None
    current_value: int | None = None


@dataclass(frozen=True, slots=True)
class AutoPurchaseDecision:
    kind: AutoPurchaseDecisionKind
    rule: AutoRefillRule
    item: ItemDefinition | None = None
    current_value: int | None = None


AUTO_REFILL_RULES: tuple[AutoRefillRule, ...] = (
    AutoRefillRule(field="satiety", threshold=35, category="food"),
    AutoRefillRule(field="energy", threshold=30, category="drink"),
    AutoRefillRule(field="health", threshold=45, category="medicine"),
    AutoRefillRule(field="cleanliness", threshold=35, category="cleaning"),
)
AUTO_REFILL_THRESHOLDS = {
    rule.field: rule.threshold
    for rule in AUTO_REFILL_RULES
}


def choose_auto_refill_item(
    *,
    state: PetState,
    inventory: dict[str, int],
    catalog: ItemCatalog,
    rules: tuple[AutoRefillRule, ...] = AUTO_REFILL_RULES,
) -> AutoRefillSelection | None:
    """选择本 tick 最应该自动使用的一个背包物品。"""

    decision = evaluate_auto_refill(
        state=state,
        inventory=inventory,
        catalog=catalog,
        rules=rules,
    )
    if decision.kind != "selected" or decision.rule is None or decision.item is None:
        return None
    return AutoRefillSelection(
        rule=decision.rule,
        item=decision.item,
        current_value=int(decision.current_value or 0),
    )


def evaluate_auto_refill(
    *,
    state: PetState,
    inventory: dict[str, int],
    catalog: ItemCatalog,
    rules: tuple[AutoRefillRule, ...] = AUTO_REFILL_RULES,
) -> AutoRefillDecision:
    """判断本 tick 的自动补状态结果，不直接修改状态或背包。"""

    candidates = _low_status_candidates(state, rules)
    if not candidates:
        return AutoRefillDecision(kind="not_triggered")

    for _danger, _index, rule, current in candidates:
        item = _first_suitable_inventory_item(
            state=state,
            inventory=inventory,
            catalog=catalog,
            rule=rule,
        )
        if item is not None:
            return AutoRefillDecision(
                kind="selected",
                rule=rule,
                item=item,
                current_value=current,
            )

    _danger, _index, rule, current = candidates[0]
    return AutoRefillDecision(
        kind="missing_stock",
        rule=rule,
        current_value=current,
    )


def choose_auto_purchase_item(
    *,
    state: PetState,
    catalog: ItemCatalog,
    rule: AutoRefillRule,
    money: int,
) -> AutoPurchaseDecision:
    """为缺货的自动补状态选择一个可买且有效的目录物品。"""

    current = int(getattr(state, rule.field))
    candidates: list[tuple[int, int, ItemDefinition]] = []
    for index, item in enumerate(catalog.items()):
        if item.category != rule.category:
            continue
        if _actual_target_lift(state, item, rule.field) <= 0:
            continue
        candidates.append((item.price, index, item))
    if not candidates:
        return AutoPurchaseDecision(
            kind="not_found",
            rule=rule,
            current_value=current,
        )

    candidates.sort()
    affordable = max(0, int(money))
    for price, _index, item in candidates:
        if price <= affordable:
            return AutoPurchaseDecision(
                kind="selected",
                rule=rule,
                item=item,
                current_value=current,
            )
    return AutoPurchaseDecision(
        kind="insufficient_money",
        rule=rule,
        item=candidates[0][2],
        current_value=current,
    )


def _low_status_candidates(
    state: PetState,
    rules: tuple[AutoRefillRule, ...],
) -> list[tuple[int, int, AutoRefillRule, int]]:
    candidates: list[tuple[int, int, AutoRefillRule, int]] = []
    for index, rule in enumerate(rules):
        current = int(getattr(state, rule.field))
        if current > rule.threshold:
            continue
        danger = rule.threshold - current
        candidates.append((-danger, index, rule, current))
    return sorted(candidates)


def _first_suitable_inventory_item(
    *,
    state: PetState,
    inventory: dict[str, int],
    catalog: ItemCatalog,
    rule: AutoRefillRule,
) -> ItemDefinition | None:
    for item in catalog.items():
        if item.category != rule.category:
            continue
        if item_count(inventory, item.id) <= 0:
            continue
        if _actual_target_lift(state, item, rule.field) <= 0:
            continue
        return item
    return None


def _actual_target_lift(
    state: PetState,
    item: ItemDefinition,
    field: AutoRefillField,
) -> int:
    effect = int(item.effects.get(field, 0))
    if effect <= 0:
        return 0
    current = int(getattr(state, field))
    return min(100, current + effect) - current


__all__ = [
    "AUTO_REFILL_RULES",
    "AUTO_REFILL_THRESHOLDS",
    "AutoRefillDecision",
    "AutoRefillDecisionKind",
    "AutoRefillField",
    "AutoRefillRule",
    "AutoRefillSelection",
    "AutoPurchaseDecision",
    "AutoPurchaseDecisionKind",
    "choose_auto_refill_item",
    "choose_auto_purchase_item",
    "evaluate_auto_refill",
]
