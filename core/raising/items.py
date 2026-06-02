"""物品目录、背包数量和最小商店逻辑。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from core.app_paths import config_path, item_icons_dir
from core.raising.pet_state import PetState

ItemCategory = Literal["food", "drink", "medicine", "cleaning", "gift"]

DEFAULT_ITEM_CATALOG = "item_catalog.json"
DEFAULT_ITEM_ICON = "default.png"
ITEM_CATEGORIES: tuple[ItemCategory, ...] = (
    "food",
    "drink",
    "medicine",
    "cleaning",
    "gift",
)
PERCENT_EFFECT_FIELDS = frozenset(
    {"satiety", "mood", "energy", "health", "cleanliness"}
)
NON_NEGATIVE_EFFECT_FIELDS = frozenset({"affection"})
ITEM_EFFECT_FIELDS = PERCENT_EFFECT_FIELDS | NON_NEGATIVE_EFFECT_FIELDS
PRIMARY_EFFECT_FIELD_BY_CATEGORY: dict[ItemCategory, str] = {
    "food": "satiety",
    "drink": "energy",
    "medicine": "health",
    "cleaning": "cleanliness",
}


@dataclass(frozen=True, slots=True)
class ItemDefinition:
    id: str
    name: str
    category: ItemCategory
    price: int
    effects: dict[str, int]
    description: str = ""
    icon: str = ""


@dataclass(frozen=True, slots=True)
class PurchaseResult:
    ok: bool
    changed: bool
    message: str
    item: ItemDefinition | None = None
    count: int = 0


@dataclass(frozen=True, slots=True)
class UseItemResult:
    ok: bool
    changed: bool
    message: str
    item: ItemDefinition | None = None
    deltas: dict[str, int] | None = None
    count: int = 0


class ItemCatalog:
    def __init__(self, items: list[ItemDefinition]) -> None:
        if not items:
            raise ValueError("物品配置不能为空")
        self._items: dict[str, ItemDefinition] = {}
        for item in items:
            if item.id in self._items:
                raise ValueError(f"物品 id 重复: {item.id}")
            self._items[item.id] = item

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "ItemCatalog":
        raw_items = data.get("items", [])
        if not isinstance(raw_items, list):
            raise ValueError("item_catalog.json 的 items 必须是列表")
        return cls([_item_from_dict(item) for item in raw_items])

    def items(self) -> tuple[ItemDefinition, ...]:
        return tuple(self._items.values())

    def get(self, item_id: str) -> ItemDefinition:
        return self._items[item_id]

    def has(self, item_id: str) -> bool:
        return item_id in self._items


def load_item_catalog(path: Path | None = None) -> ItemCatalog:
    target = path or config_path(DEFAULT_ITEM_CATALOG)
    payload = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"物品配置根节点必须是对象: {target}")
    return ItemCatalog.from_dict(payload)


def resolve_item_icon_path(
    item: ItemDefinition,
    *,
    icon_dir: Path | None = None,
) -> Path | None:
    icons = icon_dir or item_icons_dir()
    icon_name = _icon_filename(item.icon)
    if icon_name:
        icon_path = icons / icon_name
        if icon_path.is_file():
            return icon_path

    fallback = icons / DEFAULT_ITEM_ICON
    if fallback.is_file():
        return fallback
    return None


def normalize_inventory(data: object) -> dict[str, int]:
    if not isinstance(data, dict):
        return {}
    inventory: dict[str, int] = {}
    for raw_id, raw_count in data.items():
        item_id = str(raw_id).strip()
        count = _int_value(raw_count)
        if not item_id or count <= 0:
            continue
        inventory[item_id] = inventory.get(item_id, 0) + count
    return inventory


def inventory_count(inventory: dict[str, int]) -> int:
    return sum(max(0, int(count)) for count in normalize_inventory(inventory).values())


def item_count(inventory: dict[str, int], item_id: str) -> int:
    return normalize_inventory(inventory).get(str(item_id).strip(), 0)


def add_inventory_item(
    inventory: dict[str, int],
    item_id: str,
    amount: int = 1,
) -> int:
    item_id = str(item_id).strip()
    if not item_id or amount <= 0:
        return item_count(inventory, item_id)
    count = item_count(inventory, item_id) + int(amount)
    inventory[item_id] = count
    _normalize_inventory_in_place(inventory)
    return count


def remove_inventory_item(
    inventory: dict[str, int],
    item_id: str,
    amount: int = 1,
) -> int:
    item_id = str(item_id).strip()
    if not item_id or amount <= 0:
        return item_count(inventory, item_id)
    count = max(0, item_count(inventory, item_id) - int(amount))
    if count:
        inventory[item_id] = count
    else:
        inventory.pop(item_id, None)
    _normalize_inventory_in_place(inventory)
    return count


def purchase_item(
    *,
    state: PetState,
    inventory: dict[str, int],
    catalog: ItemCatalog,
    item_id: str,
) -> PurchaseResult:
    try:
        item = catalog.get(item_id)
    except KeyError:
        return PurchaseResult(False, False, f"未知物品：{item_id}")

    if state.money < item.price:
        return PurchaseResult(
            ok=False,
            changed=False,
            message=f"金币不足，购买 {item.name} 需要 {item.price} 金币。",
            item=item,
            count=item_count(inventory, item.id),
        )

    state.money = max(0, int(state.money) - item.price)
    count = add_inventory_item(inventory, item.id, 1)
    return PurchaseResult(
        ok=True,
        changed=True,
        message=f"已购买：{item.name}",
        item=item,
        count=count,
    )


def use_inventory_item(
    *,
    state: PetState,
    inventory: dict[str, int],
    catalog: ItemCatalog,
    item_id: str,
) -> UseItemResult:
    try:
        item = catalog.get(item_id)
    except KeyError:
        return UseItemResult(False, False, f"未知物品：{item_id}", deltas={})

    count = item_count(inventory, item.id)
    if count <= 0:
        return UseItemResult(
            ok=False,
            changed=False,
            message=f"背包里没有 {item.name}。",
            item=item,
            deltas={},
            count=0,
        )

    if not item_has_actual_improvement(state, item):
        return UseItemResult(
            ok=False,
            changed=False,
            message=f"{item.name} 现在用不上，状态已经足够好了。",
            item=item,
            deltas={},
            count=count,
        )

    deltas = apply_item_effects(state, item.effects)
    count = remove_inventory_item(inventory, item.id, 1)
    return UseItemResult(
        ok=True,
        changed=True,
        message=f"已使用：{item.name}",
        item=item,
        deltas=deltas,
        count=count,
    )


def item_has_actual_improvement(state: PetState, item: ItemDefinition) -> bool:
    """判断物品当前是否值得消耗；主要状态满了时不靠附带效果误用。"""

    deltas = preview_item_effects(state, item.effects)
    primary_field = PRIMARY_EFFECT_FIELD_BY_CATEGORY.get(item.category)
    if primary_field in item.effects:
        return deltas.get(primary_field, 0) > 0
    return any(delta > 0 for delta in deltas.values())


def preview_item_effects(state: PetState, effects: dict[str, int]) -> dict[str, int]:
    actual_deltas: dict[str, int] = {}
    for field, delta in effects.items():
        if field not in ITEM_EFFECT_FIELDS or delta == 0:
            continue
        old_value = int(getattr(state, field))
        if field in PERCENT_EFFECT_FIELDS:
            new_value = _clamp_percent(old_value + int(delta))
        else:
            new_value = max(0, old_value + int(delta))
        if new_value == old_value:
            continue
        actual_deltas[field] = new_value - old_value
    return actual_deltas


def apply_item_effects(state: PetState, effects: dict[str, int]) -> dict[str, int]:
    actual_deltas = preview_item_effects(state, effects)
    for field, delta in actual_deltas.items():
        setattr(state, field, int(getattr(state, field)) + delta)
    return actual_deltas


def _normalize_inventory_in_place(inventory: dict[str, int]) -> None:
    normalized = normalize_inventory(inventory)
    inventory.clear()
    inventory.update(normalized)


def _item_from_dict(data: object) -> ItemDefinition:
    if not isinstance(data, dict):
        raise ValueError("单个物品配置必须是对象")
    item_id = _required_text(data, "id")
    category = _category_value(data.get("category"), item_id)
    return ItemDefinition(
        id=item_id,
        name=_required_text(data, "name"),
        category=category,
        price=max(0, _int_value(data.get("price", 0))),
        effects=_effects(data.get("effects", {}), item_id),
        description=_optional_text(data.get("description")),
        icon=_optional_text(data.get("icon")),
    )


def _effects(data: object, item_id: str) -> dict[str, int]:
    if not isinstance(data, dict):
        raise ValueError(f"{item_id}.effects 必须是对象")
    effects: dict[str, int] = {}
    for raw_field, raw_delta in data.items():
        field = str(raw_field).strip()
        if field not in ITEM_EFFECT_FIELDS:
            raise ValueError(f"{item_id}.effects 包含未知字段: {field}")
        delta = _int_value(raw_delta)
        if delta:
            effects[field] = delta
    if not effects:
        raise ValueError(f"{item_id}.effects 不能为空")
    return effects


def _category_value(value: object, item_id: str) -> ItemCategory:
    text = str(value or "").strip()
    if text not in ITEM_CATEGORIES:
        raise ValueError(f"{item_id}.category 必须是 {', '.join(ITEM_CATEGORIES)} 之一")
    return text  # type: ignore[return-value]


def _required_text(data: dict[str, object], key: str) -> str:
    value = str(data.get(key, "")).strip()
    if not value:
        raise ValueError(f"物品配置缺少字段: {key}")
    return value


def _optional_text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _icon_filename(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if "/" in text or "\\" in text:
        return ""
    path = Path(text)
    if path.is_absolute() or path.name != text:
        return ""
    return text


def _int_value(value: object) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _clamp_percent(value: int) -> int:
    return min(100, max(0, int(value)))


__all__ = [
    "DEFAULT_ITEM_CATALOG",
    "DEFAULT_ITEM_ICON",
    "ITEM_CATEGORIES",
    "ITEM_EFFECT_FIELDS",
    "ItemCatalog",
    "ItemCategory",
    "ItemDefinition",
    "PRIMARY_EFFECT_FIELD_BY_CATEGORY",
    "PurchaseResult",
    "UseItemResult",
    "add_inventory_item",
    "apply_item_effects",
    "inventory_count",
    "item_has_actual_improvement",
    "item_count",
    "load_item_catalog",
    "normalize_inventory",
    "preview_item_effects",
    "purchase_item",
    "remove_inventory_item",
    "resolve_item_icon_path",
    "use_inventory_item",
]
