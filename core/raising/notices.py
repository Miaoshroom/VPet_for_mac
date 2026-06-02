"""养成流程提示文案"""

from __future__ import annotations

from core.raising.auto_refill import AutoRefillRule


def join_notice(*parts: str) -> str:
    return "；".join(part for part in (str(part).strip() for part in parts) if part)


def care_action_for_item_category(category: str) -> str:
    if category == "food":
        return "simple_feed"
    if category == "drink":
        return "drink"
    if category == "cleaning":
        return "simple_clean"
    if category == "gift":
        return "gift"
    return "medicine"


def format_item_deltas(deltas: dict[str, int]) -> str:
    labels = {
        "satiety": "饱腹",
        "mood": "心情",
        "energy": "体力",
        "health": "健康",
        "cleanliness": "清洁",
        "affection": "亲密度",
    }
    parts = [
        f"{labels.get(field, field)} {'+' if amount > 0 else ''}{amount}"
        for field, amount in deltas.items()
        if amount
    ]
    return "、".join(parts)


def auto_refill_missing_notice(rule: AutoRefillRule) -> str:
    status_labels = {
        "satiety": "饱腹",
        "energy": "体力",
        "health": "健康",
        "cleanliness": "清洁",
    }
    category_labels = {
        "food": "食物",
        "drink": "饮料",
        "medicine": "药品",
        "cleaning": "清洁用品",
        "gift": "礼物",
    }
    status = status_labels.get(rule.field, rule.field)
    category = category_labels.get(rule.category, rule.category)
    return f"{status}过低，但背包没有合适的{category}"


def auto_purchase_insufficient_money_notice(
    rule: AutoRefillRule,
    item_name: str,
    price: int,
) -> str:
    status_labels = {
        "satiety": "饱腹",
        "energy": "体力",
        "health": "健康",
        "cleanliness": "清洁",
    }
    status = status_labels.get(rule.field, rule.field)
    return f"{status}过低，金币不足，无法自动购买{item_name}（需要 {price} 金币）"
