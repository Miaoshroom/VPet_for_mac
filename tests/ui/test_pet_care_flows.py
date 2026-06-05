from __future__ import annotations

import json
import os
import sys
from pathlib import Path
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = next(path for path in Path(__file__).resolve().parents if (path / "main.py").is_file())
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.raising.activity import ActivitySnapshot, load_activity_catalog
from core.raising.activity_playback import CarePlaybackResult, PlaybackStartCheck
from core.raising.auto_refill import (
    AUTO_REFILL_RULES,
    choose_auto_purchase_item,
    choose_auto_refill_item,
    evaluate_auto_refill,
)
from core.raising.items import (
    ItemCatalog,
    ItemDefinition,
    inventory_count,
    load_item_catalog,
    purchase_item,
    resolve_item_icon_path,
    use_inventory_item,
)
from core.raising.pet_state import PetState
from core.raising.save_game import SaveGame, load_save_game, write_save_game
from ui.pet_window import PetWindow

SHOP_VISIBLE_ACTION_LIMIT_MS = 120
SHOP_HIDDEN_SYNC_LIMIT_MS = 30
SHOP_LARGE_OPEN_LIMIT_MS = 120
SHOP_DISPLAY_ALL_LIMIT_MS = 50
SHOP_ROW_BATCH_LIMIT_MS = 80
SHOP_ICON_SECOND_REFRESH_LIMIT_MS = 80
STATUS_PANEL_HOVER_LIMIT_MS = 50


def _catalog() -> ItemCatalog:
    return ItemCatalog(
        [
            ItemDefinition(
                id="rice_ball",
                name="饭团",
                category="food",
                price=12,
                effects={"satiety": 24, "mood": 2},
                description="小份主食，适合快速补充饱腹。",
                icon="rice_ball.png",
            ),
            ItemDefinition(
                id="basic_medicine",
                name="基础药品",
                category="medicine",
                price=24,
                effects={"health": 22},
                icon="basic_medicine.png",
            ),
            ItemDefinition(
                id="sparkling_water",
                name="气泡水",
                category="drink",
                price=10,
                effects={"energy": 6, "mood": 3},
                icon="sparkling_water.png",
            ),
            ItemDefinition(
                id="party_drink",
                name="派对饮料",
                category="drink",
                price=18,
                effects={"mood": 12},
            ),
            ItemDefinition(
                id="cleaning_wipes",
                name="清洁湿巾",
                category="cleaning",
                price=14,
                effects={"cleanliness": 28, "mood": 1},
                icon="cleaning_wipes.png",
            ),
            ItemDefinition(
                id="gift_box",
                name="礼物盒子",
                category="gift",
                price=30,
                effects={"mood": 10, "affection": 3},
                icon="礼物盒子.png",
            ),
        ]
    )


class ItemIconPathSmokeTest(unittest.TestCase):
    def _item(self, icon: str = "") -> ItemDefinition:
        return ItemDefinition(
            id="test_item",
            name="测试物品",
            category="food",
            price=1,
            effects={"satiety": 1},
            icon=icon,
        )

    def test_existing_icon_resolves_to_configured_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            icon_dir = Path(tmp_dir)
            icon_path = icon_dir / "food.png"
            icon_path.write_bytes(b"icon")
            (icon_dir / "default.png").write_bytes(b"default")

            resolved = resolve_item_icon_path(
                self._item("food.png"),
                icon_dir=icon_dir,
            )

        self.assertEqual(resolved, icon_path)

    def test_missing_icon_field_uses_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            icon_dir = Path(tmp_dir)
            fallback = icon_dir / "default.png"
            fallback.write_bytes(b"default")

            resolved = resolve_item_icon_path(self._item(), icon_dir=icon_dir)

        self.assertEqual(resolved, fallback)

    def test_missing_icon_file_uses_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            icon_dir = Path(tmp_dir)
            fallback = icon_dir / "default.png"
            fallback.write_bytes(b"default")

            resolved = resolve_item_icon_path(
                self._item("missing.png"),
                icon_dir=icon_dir,
            )

        self.assertEqual(resolved, fallback)

    def test_missing_fallback_returns_none_without_crashing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            resolved = resolve_item_icon_path(
                self._item("missing.png"),
                icon_dir=Path(tmp_dir),
            )

        self.assertIsNone(resolved)

    def test_bundled_catalog_icons_resolve(self) -> None:
        catalog = load_item_catalog()

        for item in catalog.items():
            self.assertTrue(item.icon)
            self.assertIsNotNone(resolve_item_icon_path(item))


class ItemLogicSmokeTest(unittest.TestCase):
    def test_purchase_success_spends_money_and_adds_inventory(self) -> None:
        save = SaveGame(pet_state=PetState(money=20))

        result = purchase_item(
            state=save.pet_state,
            inventory=save.inventory,
            catalog=_catalog(),
            item_id="rice_ball",
        )

        self.assertTrue(result.ok)
        self.assertTrue(result.changed)
        self.assertEqual(save.pet_state.money, 8)
        self.assertEqual(save.inventory, {"rice_ball": 1})
        self.assertEqual(result.count, 1)

    def test_purchase_insufficient_money_does_not_change_inventory(self) -> None:
        save = SaveGame(pet_state=PetState(money=2))

        result = purchase_item(
            state=save.pet_state,
            inventory=save.inventory,
            catalog=_catalog(),
            item_id="rice_ball",
        )

        self.assertFalse(result.ok)
        self.assertFalse(result.changed)
        self.assertIn("金币不足", result.message)
        self.assertEqual(save.pet_state.money, 2)
        self.assertEqual(save.inventory, {})

    def test_use_success_applies_effects_and_removes_zero_count_item(self) -> None:
        save = SaveGame(
            pet_state=PetState(satiety=40, mood=40),
            inventory={"rice_ball": 1},
        )

        result = use_inventory_item(
            state=save.pet_state,
            inventory=save.inventory,
            catalog=_catalog(),
            item_id="rice_ball",
        )

        self.assertTrue(result.ok)
        self.assertTrue(result.changed)
        self.assertEqual(save.pet_state.satiety, 64)
        self.assertEqual(save.pet_state.mood, 42)
        self.assertEqual(result.deltas, {"satiety": 24, "mood": 2})
        self.assertEqual(save.inventory, {})
        self.assertEqual(result.count, 0)

    def test_use_full_primary_status_does_not_consume_item(self) -> None:
        save = SaveGame(
            pet_state=PetState(satiety=100, mood=40),
            inventory={"rice_ball": 1},
        )

        result = use_inventory_item(
            state=save.pet_state,
            inventory=save.inventory,
            catalog=_catalog(),
            item_id="rice_ball",
        )

        self.assertFalse(result.ok)
        self.assertFalse(result.changed)
        self.assertIn("用不上", result.message)
        self.assertEqual(save.pet_state.satiety, 100)
        self.assertEqual(save.pet_state.mood, 40)
        self.assertEqual(save.inventory, {"rice_ball": 1})
        self.assertEqual(result.deltas, {})
        self.assertEqual(result.count, 1)

    def test_use_quantity_missing_does_not_change_state(self) -> None:
        save = SaveGame(pet_state=PetState(satiety=40), inventory={})

        result = use_inventory_item(
            state=save.pet_state,
            inventory=save.inventory,
            catalog=_catalog(),
            item_id="rice_ball",
        )

        self.assertFalse(result.ok)
        self.assertFalse(result.changed)
        self.assertIn("背包里没有", result.message)
        self.assertEqual(save.pet_state.satiety, 40)
        self.assertEqual(save.inventory, {})

    def test_save_game_normalizes_old_or_dirty_inventory_shapes(self) -> None:
        save = SaveGame.from_dict(
            {
                "pet_state": {"money": 7},
                "inventory": {
                    "rice_ball": "2",
                    "basic_medicine": 0,
                    "bad": -3,
                    "": 8,
                },
            }
        )

        self.assertEqual(save.inventory, {"rice_ball": 2})
        self.assertEqual(save.to_dict()["inventory"], {"rice_ball": 2})

    def test_save_game_round_trip_keeps_inventory_counts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "savegame.json"
            save = SaveGame(
                pet_state=PetState(money=5),
                inventory={"rice_ball": 2, "basic_medicine": 1},
            )

            write_save_game(save, path)
            loaded = load_save_game(path)

        self.assertEqual(loaded.inventory, {"rice_ball": 2, "basic_medicine": 1})
        self.assertEqual(inventory_count(loaded.inventory), 3)

    def test_save_game_old_payload_defaults_auto_purchase_off(self) -> None:
        save = SaveGame.from_dict(
            {
                "version": 2,
                "pet_state": {"money": 7},
                "inventory": {"rice_ball": 1},
                "auto_refill_enabled": True,
            }
        )

        self.assertTrue(save.auto_refill_enabled)
        self.assertFalse(save.auto_purchase_enabled)
        self.assertFalse(save.to_dict()["auto_purchase_enabled"])

    def test_bundled_item_catalog_loads_all_required_categories(self) -> None:
        catalog = load_item_catalog()
        categories = {item.category for item in catalog.items()}

        self.assertGreaterEqual(
            categories,
            {"food", "drink", "medicine", "cleaning", "gift"},
        )

    def test_gift_can_be_used_even_when_mood_is_full(self) -> None:
        save = SaveGame(
            pet_state=PetState(mood=100, affection=2),
            inventory={"gift_box": 1},
        )

        result = use_inventory_item(
            state=save.pet_state,
            inventory=save.inventory,
            catalog=_catalog(),
            item_id="gift_box",
        )

        self.assertTrue(result.ok)
        self.assertTrue(result.changed)
        self.assertEqual(save.pet_state.mood, 100)
        self.assertEqual(save.pet_state.affection, 5)
        self.assertEqual(result.deltas, {"affection": 3})
        self.assertEqual(save.inventory, {})

    def test_auto_refill_selects_most_dangerous_suitable_item(self) -> None:
        save = SaveGame(
            pet_state=PetState(satiety=25, health=20),
            inventory={"rice_ball": 1, "basic_medicine": 1},
        )

        selection = choose_auto_refill_item(
            state=save.pet_state,
            inventory=save.inventory,
            catalog=_catalog(),
        )

        self.assertIsNotNone(selection)
        self.assertEqual(selection.rule.field, "health")
        self.assertEqual(selection.item.id, "basic_medicine")

    def test_auto_refill_tie_uses_rule_order_stably(self) -> None:
        save = SaveGame(
            pet_state=PetState(satiety=25, energy=20),
            inventory={"rice_ball": 1, "sparkling_water": 1},
        )

        selection = choose_auto_refill_item(
            state=save.pet_state,
            inventory=save.inventory,
            catalog=_catalog(),
        )

        self.assertIsNotNone(selection)
        self.assertEqual(selection.rule.field, "satiety")
        self.assertEqual(selection.item.id, "rice_ball")

    def test_auto_refill_ignores_mood_only_items_for_energy(self) -> None:
        save = SaveGame(
            pet_state=PetState(energy=20),
            inventory={"party_drink": 1},
        )

        selection = choose_auto_refill_item(
            state=save.pet_state,
            inventory=save.inventory,
            catalog=_catalog(),
        )

        self.assertIsNone(selection)

    def test_auto_refill_reports_missing_stock_for_low_target(self) -> None:
        save = SaveGame(
            pet_state=PetState(energy=20),
            inventory={"party_drink": 1},
        )

        decision = evaluate_auto_refill(
            state=save.pet_state,
            inventory=save.inventory,
            catalog=_catalog(),
        )

        self.assertEqual(decision.kind, "missing_stock")
        self.assertIsNotNone(decision.rule)
        self.assertEqual(decision.rule.field, "energy")
        self.assertEqual(decision.rule.category, "drink")

    def test_auto_refill_does_not_treat_low_mood_as_a_target(self) -> None:
        save = SaveGame(
            pet_state=PetState(mood=10),
            inventory={"party_drink": 1, "sparkling_water": 1},
        )

        selection = choose_auto_refill_item(
            state=save.pet_state,
            inventory=save.inventory,
            catalog=_catalog(),
        )

        self.assertIsNone(selection)

    def test_auto_purchase_selects_lowest_price_effective_catalog_item(self) -> None:
        catalog = ItemCatalog(
            [
                ItemDefinition(
                    id="fancy_food",
                    name="豪华餐",
                    category="food",
                    price=50,
                    effects={"satiety": 45},
                ),
                ItemDefinition(
                    id="cheap_food",
                    name="小饭团",
                    category="food",
                    price=8,
                    effects={"satiety": 10},
                ),
                ItemDefinition(
                    id="mood_snack",
                    name="开心零食",
                    category="food",
                    price=2,
                    effects={"mood": 12},
                ),
            ]
        )

        decision = choose_auto_purchase_item(
            state=PetState(satiety=20, money=50),
            catalog=catalog,
            rule=AUTO_REFILL_RULES[0],
            money=50,
        )

        self.assertEqual(decision.kind, "selected")
        self.assertIsNotNone(decision.item)
        self.assertEqual(decision.item.id, "cheap_food")


class FakeCarePlayback:
    def __init__(self, check: PlaybackStartCheck, message: str = "") -> None:
        self.check = check
        self.message = message
        self.started: list[str] = []
        self.started_items: list[str | None] = []

    def can_start_care(self) -> PlaybackStartCheck:
        return self.check

    def start_care_animation(
        self,
        care_action_id: str,
        *,
        item: ItemDefinition | None = None,
    ) -> CarePlaybackResult:
        self.started.append(care_action_id)
        self.started_items.append(item.id if item is not None else None)
        return CarePlaybackResult(False, None, self.message)


class FakeStatusPanel:
    def __init__(self) -> None:
        self.notice = ""
        self.notices: list[str] = []
        self.inventory_calls: list[tuple[dict[str, int], int]] = []
        self.pet_state_money: list[int] = []

    def set_care_notice(self, message: str) -> None:
        self.notice = message
        self.notices.append(message)

    def set_inventory(self, inventory: dict[str, int], *, money: int) -> None:
        self.inventory_calls.append((dict(inventory), int(money)))

    def set_pet_state(
        self,
        state: PetState,
        *,
        current_visual_state: str | None = None,
    ) -> None:
        del current_visual_state
        self.pet_state_money.append(int(state.money))


class FakeShopInventoryWindow:
    def __init__(self) -> None:
        self.notices: list[str] = []
        self.inventory_calls: list[dict[str, int]] = []
        self.pet_state_money: list[int] = []

    def set_notice(self, message: str) -> None:
        self.notices.append(message)

    def set_inventory(self, inventory: dict[str, int]) -> None:
        self.inventory_calls.append(dict(inventory))

    def set_pet_state(self, state: PetState) -> None:
        self.pet_state_money.append(int(state.money))


class HiddenFakeShopInventoryWindow(FakeShopInventoryWindow):
    def __init__(self) -> None:
        super().__init__()
        self.dirty_count = 0
        self.visible = False

    def isVisible(self) -> bool:
        return self.visible

    def mark_dirty(self) -> None:
        self.dirty_count += 1


class FakeDirector:
    def pet_state(self) -> str:
        return "normal"


class FakeTicker:
    def __init__(self) -> None:
        self.reset_count = 0

    def reset(self) -> None:
        self.reset_count += 1


class FakeSignal:
    def __init__(self) -> None:
        self.emit_count = 0

    def emit(self) -> None:
        self.emit_count += 1


class FakeRuntimePlugin:
    PLUGIN_NAME = "show_sticker"

    def __init__(self, title: str = "发表情", enabled: bool = True) -> None:
        self._title = title
        self.enabled = enabled
        self.set_calls: list[bool] = []

    def menu_title(self) -> str:
        return self._title

    def is_enabled(self) -> bool:
        return self.enabled

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = bool(enabled)
        self.set_calls.append(self.enabled)


class FakeTomatoClockPlugin:
    PLUGIN_NAME = "tomato_clock"

    def __init__(self) -> None:
        self.running = False
        self.paused = False
        self.set_calls: list[bool] = []

    def build_menu(self, _menu) -> None:
        return

    def is_running(self) -> bool:
        return self.running

    def is_paused(self) -> bool:
        return self.paused

    def set_running(self, enabled: bool) -> None:
        self.running = bool(enabled)
        self.set_calls.append(self.running)


class FakeCustomStatusPanel:
    def __init__(self) -> None:
        self.plugin_toggles: list[tuple[tuple[str, str, bool], ...]] = []
        self.tomato_states: list[dict[str, bool]] = []

    def set_plugin_toggles(self, toggles: tuple[tuple[str, str, bool], ...]) -> None:
        self.plugin_toggles.append(tuple(toggles))

    def set_tomato_clock_state(
        self,
        *,
        available: bool,
        running: bool,
        paused: bool = False,
    ) -> None:
        self.tomato_states.append(
            {
                "available": bool(available),
                "running": bool(running),
                "paused": bool(paused),
            }
        )


class ItemUseWindowBoundarySmokeTest(unittest.TestCase):
    def _window_like(self, save: SaveGame, care: FakeCarePlayback):
        window = type("WindowLike", (), {})()
        window._save_game = save
        window._item_catalog = _catalog()
        window._care_playback = care
        window._status_ticker = FakeTicker()
        window._status_panel = FakeStatusPanel()
        window.save_game_changed = FakeSignal()
        window._request_visual_state_update = lambda: None
        window._sync_status_panel_info = lambda: None
        window._sync_inventory_panel = lambda: None
        return window

    def test_manual_item_use_routes_each_category_through_care_bridge(self) -> None:
        cases = (
            ("rice_ball", PetState(satiety=40, mood=40), "simple_feed", "satiety", 64),
            ("sparkling_water", PetState(energy=40, mood=40), "drink", "energy", 46),
            (
                "cleaning_wipes",
                PetState(cleanliness=40, mood=40),
                "simple_clean",
                "cleanliness",
                68,
            ),
            ("basic_medicine", PetState(health=40), "medicine", "health", 62),
            ("gift_box", PetState(mood=100, affection=2), "gift", "affection", 5),
        )
        for item_id, state, care_action_id, field, expected_value in cases:
            with self.subTest(item_id=item_id):
                save = SaveGame(pet_state=state, inventory={item_id: 1})
                window = self._window_like(
                    save,
                    FakeCarePlayback(PlaybackStartCheck(True)),
                )

                PetWindow._use_item(window, item_id)

                self.assertEqual(getattr(save.pet_state, field), expected_value)
                self.assertEqual(save.inventory, {})
                self.assertEqual(window._care_playback.started, [care_action_id])
                self.assertEqual(window._care_playback.started_items, [item_id])
                self.assertEqual(window._status_ticker.reset_count, 1)
                self.assertEqual(window.save_game_changed.emit_count, 1)

    def test_item_use_blocked_by_playback_does_not_deduct_item_or_change_state(self) -> None:
        save = SaveGame(
            pet_state=PetState(satiety=40),
            inventory={"rice_ball": 1},
        )
        window = self._window_like(
            save,
            FakeCarePlayback(PlaybackStartCheck(False, "当前动作占用中，稍后再照顾。")),
        )

        PetWindow._use_item(window, "rice_ball")

        self.assertEqual(save.pet_state.satiety, 40)
        self.assertEqual(save.inventory, {"rice_ball": 1})
        self.assertEqual(window._status_ticker.reset_count, 0)
        self.assertEqual(window.save_game_changed.emit_count, 0)
        self.assertIn("当前动作占用", window._status_panel.notice)

    def test_missing_animation_still_uses_item_and_does_not_crash(self) -> None:
        save = SaveGame(
            pet_state=PetState(health=30),
            inventory={"basic_medicine": 1},
        )
        window = self._window_like(
            save,
            FakeCarePlayback(
                PlaybackStartCheck(True),
                "照顾成功，但当前表现状态没有可用照顾动画。",
            ),
        )

        PetWindow._use_item(window, "basic_medicine")

        self.assertEqual(save.pet_state.health, 52)
        self.assertEqual(save.inventory, {})
        self.assertEqual(window._care_playback.started, ["medicine"])
        self.assertEqual(window._status_ticker.reset_count, 1)
        self.assertEqual(window.save_game_changed.emit_count, 1)
        self.assertIn("没有可用照顾动画", window._status_panel.notice)


class AutoRefillWindowSmokeTest(unittest.TestCase):
    def _window_like(self, save: SaveGame, care: FakeCarePlayback):
        window = type("WindowLike", (), {})()
        window._save_game = save
        window._item_catalog = _catalog()
        window._care_playback = care
        window._status_ticker = FakeTicker()
        window._status_panel = FakeStatusPanel()
        window.save_game_changed = FakeSignal()
        window._request_visual_state_update = lambda: None
        window._sync_status_panel_info = lambda: None
        window._sync_inventory_panel = lambda: None
        window._auto_refill_missing_notice_shown_at = {}
        window._auto_refill_missing_notice_interval_seconds = 900.0
        window._auto_refill_test_now = 0.0
        window._auto_refill_notice_clock = lambda: window._auto_refill_test_now
        return window

    def test_auto_refill_success_uses_one_backpack_item(self) -> None:
        save = SaveGame(
            pet_state=PetState(satiety=35),
            inventory={"rice_ball": 1, "basic_medicine": 1},
            auto_refill_enabled=True,
        )
        window = self._window_like(save, FakeCarePlayback(PlaybackStartCheck(True)))

        changed = PetWindow._try_auto_refill_after_tick(window)

        self.assertTrue(changed)
        self.assertEqual(save.pet_state.satiety, 59)
        self.assertEqual(save.inventory, {"basic_medicine": 1})
        self.assertEqual(window._care_playback.started, ["simple_feed"])
        self.assertEqual(window._care_playback.started_items, ["rice_ball"])
        self.assertEqual(window._status_ticker.reset_count, 1)
        self.assertEqual(window.save_game_changed.emit_count, 1)
        self.assertIn("自动使用了饭团", window._status_panel.notice)

    def test_auto_refill_uses_at_most_one_item_when_multiple_states_are_low(self) -> None:
        save = SaveGame(
            pet_state=PetState(satiety=25, health=20),
            inventory={"rice_ball": 1, "basic_medicine": 1},
            auto_refill_enabled=True,
        )
        window = self._window_like(save, FakeCarePlayback(PlaybackStartCheck(True)))

        changed = PetWindow._try_auto_refill_after_tick(window)

        self.assertTrue(changed)
        self.assertEqual(save.pet_state.satiety, 25)
        self.assertEqual(save.pet_state.health, 42)
        self.assertEqual(save.inventory, {"rice_ball": 1})
        self.assertEqual(window._care_playback.started, ["medicine"])
        self.assertEqual(window._care_playback.started_items, ["basic_medicine"])
        self.assertEqual(window.save_game_changed.emit_count, 1)

    def test_auto_refill_routes_drink_and_cleaning_categories(self) -> None:
        cases = (
            (
                SaveGame(
                    pet_state=PetState(energy=30),
                    inventory={"sparkling_water": 1},
                    auto_refill_enabled=True,
                ),
                "drink",
                "energy",
                36,
            ),
            (
                SaveGame(
                    pet_state=PetState(cleanliness=35),
                    inventory={"cleaning_wipes": 1},
                    auto_refill_enabled=True,
                ),
                "simple_clean",
                "cleanliness",
                63,
            ),
        )
        for save, care_action_id, field, expected_value in cases:
            with self.subTest(care_action_id=care_action_id):
                window = self._window_like(
                    save,
                    FakeCarePlayback(PlaybackStartCheck(True)),
                )

                changed = PetWindow._try_auto_refill_after_tick(window)

                self.assertTrue(changed)
                self.assertEqual(getattr(save.pet_state, field), expected_value)
                self.assertEqual(save.inventory, {})
                self.assertEqual(window._care_playback.started, [care_action_id])
                self.assertEqual(len(window._care_playback.started_items), 1)
                self.assertEqual(window.save_game_changed.emit_count, 1)

    def test_auto_refill_disabled_does_not_use_item(self) -> None:
        save = SaveGame(
            pet_state=PetState(satiety=35),
            inventory={"rice_ball": 1},
            auto_refill_enabled=False,
        )
        window = self._window_like(save, FakeCarePlayback(PlaybackStartCheck(True)))

        changed = PetWindow._try_auto_refill_after_tick(window)

        self.assertFalse(changed)
        self.assertEqual(save.pet_state.satiety, 35)
        self.assertEqual(save.inventory, {"rice_ball": 1})
        self.assertEqual(window._care_playback.started, [])
        self.assertEqual(window.save_game_changed.emit_count, 0)

    def test_auto_refill_disabled_does_not_show_missing_stock_notice(self) -> None:
        save = SaveGame(
            pet_state=PetState(satiety=35),
            inventory={},
            auto_refill_enabled=False,
        )
        window = self._window_like(save, FakeCarePlayback(PlaybackStartCheck(True)))

        changed = PetWindow._try_auto_refill_after_tick(window)

        self.assertFalse(changed)
        self.assertEqual(window._status_panel.notices, [])

    def test_auto_refill_empty_inventory_does_not_change_anything(self) -> None:
        save = SaveGame(
            pet_state=PetState(satiety=35),
            inventory={},
            auto_refill_enabled=True,
        )
        window = self._window_like(save, FakeCarePlayback(PlaybackStartCheck(True)))

        changed = PetWindow._try_auto_refill_after_tick(window)

        self.assertFalse(changed)
        self.assertEqual(save.pet_state.satiety, 35)
        self.assertEqual(save.inventory, {})
        self.assertEqual(window._care_playback.started, [])
        self.assertEqual(window.save_game_changed.emit_count, 0)
        self.assertIn("饱腹过低", window._status_panel.notice)
        self.assertIn("食物", window._status_panel.notice)

    def test_auto_refill_missing_stock_notice_is_throttled_by_field(self) -> None:
        save = SaveGame(
            pet_state=PetState(satiety=35),
            inventory={},
            auto_refill_enabled=True,
        )
        window = self._window_like(save, FakeCarePlayback(PlaybackStartCheck(True)))

        PetWindow._try_auto_refill_after_tick(window)
        PetWindow._try_auto_refill_after_tick(window)
        window._auto_refill_test_now = 901.0
        PetWindow._try_auto_refill_after_tick(window)

        self.assertEqual(len(window._status_panel.notices), 2)
        self.assertTrue(
            all("饱腹过低" in notice for notice in window._status_panel.notices)
        )

    def test_auto_refill_missing_notice_state_stays_out_of_save_game(self) -> None:
        save = SaveGame(
            pet_state=PetState(satiety=35),
            inventory={},
            auto_refill_enabled=True,
        )
        window = self._window_like(save, FakeCarePlayback(PlaybackStartCheck(True)))

        PetWindow._try_auto_refill_after_tick(window)

        self.assertEqual(window._auto_refill_missing_notice_shown_at, {"satiety": 0.0})
        self.assertNotIn("auto_refill_missing_notice", str(save.to_dict()))

    def test_auto_refill_missing_stock_notice_is_not_globally_throttled(self) -> None:
        save = SaveGame(
            pet_state=PetState(satiety=35),
            inventory={},
            auto_refill_enabled=True,
        )
        window = self._window_like(save, FakeCarePlayback(PlaybackStartCheck(True)))

        PetWindow._try_auto_refill_after_tick(window)
        save.pet_state.satiety = 50
        save.pet_state.energy = 30
        PetWindow._try_auto_refill_after_tick(window)

        self.assertEqual(len(window._status_panel.notices), 2)
        self.assertIn("饱腹过低", window._status_panel.notices[0])
        self.assertIn("体力过低", window._status_panel.notices[1])

    def test_auto_refill_success_resets_missing_stock_notice_for_field(self) -> None:
        save = SaveGame(
            pet_state=PetState(satiety=35),
            inventory={},
            auto_refill_enabled=True,
        )
        window = self._window_like(save, FakeCarePlayback(PlaybackStartCheck(True)))

        PetWindow._try_auto_refill_after_tick(window)
        save.inventory["rice_ball"] = 1
        changed = PetWindow._try_auto_refill_after_tick(window)
        save.pet_state.satiety = 20
        PetWindow._try_auto_refill_after_tick(window)

        self.assertTrue(changed)
        self.assertEqual(len(window._status_panel.notices), 3)
        self.assertIn("自动使用了饭团", window._status_panel.notices[1])
        self.assertIn("饱腹过低", window._status_panel.notices[2])

    def test_auto_refill_busy_playback_does_not_deduct_item(self) -> None:
        save = SaveGame(
            pet_state=PetState(satiety=35),
            inventory={"rice_ball": 1},
            auto_refill_enabled=True,
        )
        window = self._window_like(
            save,
            FakeCarePlayback(PlaybackStartCheck(False, "当前动作占用中，稍后再照顾。")),
        )

        changed = PetWindow._try_auto_refill_after_tick(window)

        self.assertFalse(changed)
        self.assertEqual(save.pet_state.satiety, 35)
        self.assertEqual(save.inventory, {"rice_ball": 1})
        self.assertEqual(window._care_playback.started, [])
        self.assertEqual(window.save_game_changed.emit_count, 0)
        self.assertEqual(window._status_panel.notice, "")
        self.assertEqual(window._status_panel.notices, [])

    def test_auto_refill_above_threshold_does_not_use_item(self) -> None:
        save = SaveGame(
            pet_state=PetState(satiety=36),
            inventory={"rice_ball": 1},
            auto_refill_enabled=True,
        )
        window = self._window_like(save, FakeCarePlayback(PlaybackStartCheck(True)))

        changed = PetWindow._try_auto_refill_after_tick(window)

        self.assertFalse(changed)
        self.assertEqual(save.pet_state.satiety, 36)
        self.assertEqual(save.inventory, {"rice_ball": 1})
        self.assertEqual(window._care_playback.started, [])
        self.assertEqual(window._status_panel.notices, [])

    def test_auto_refill_low_mood_does_not_use_item_or_show_notice(self) -> None:
        save = SaveGame(
            pet_state=PetState(mood=10),
            inventory={"party_drink": 1},
            auto_refill_enabled=True,
        )
        window = self._window_like(save, FakeCarePlayback(PlaybackStartCheck(True)))

        changed = PetWindow._try_auto_refill_after_tick(window)

        self.assertFalse(changed)
        self.assertEqual(save.pet_state.mood, 10)
        self.assertEqual(save.inventory, {"party_drink": 1})
        self.assertEqual(window._care_playback.started, [])
        self.assertEqual(window._status_panel.notices, [])

    def test_auto_refill_missing_animation_still_applies_item(self) -> None:
        save = SaveGame(
            pet_state=PetState(health=30),
            inventory={"basic_medicine": 1},
            auto_refill_enabled=True,
        )
        window = self._window_like(
            save,
            FakeCarePlayback(
                PlaybackStartCheck(True),
                "照顾成功，但当前表现状态没有可用照顾动画。",
            ),
        )

        changed = PetWindow._try_auto_refill_after_tick(window)

        self.assertTrue(changed)
        self.assertEqual(save.pet_state.health, 52)
        self.assertEqual(save.inventory, {})
        self.assertEqual(window._care_playback.started, ["medicine"])
        self.assertEqual(window.save_game_changed.emit_count, 1)
        self.assertIn("自动使用了基础药品", window._status_panel.notice)
        self.assertIn("没有可用照顾动画", window._status_panel.notice)

    def test_auto_purchase_disabled_missing_stock_does_not_buy(self) -> None:
        save = SaveGame(
            pet_state=PetState(satiety=35, money=20),
            inventory={},
            auto_refill_enabled=True,
            auto_purchase_enabled=False,
        )
        window = self._window_like(save, FakeCarePlayback(PlaybackStartCheck(True)))

        changed = PetWindow._try_auto_refill_after_tick(window)

        self.assertFalse(changed)
        self.assertEqual(save.pet_state.money, 20)
        self.assertEqual(save.inventory, {})
        self.assertEqual(window._care_playback.started, [])
        self.assertIn("背包没有合适的食物", window._status_panel.notice)

    def test_auto_purchase_enabled_buys_and_uses_affordable_item(self) -> None:
        save = SaveGame(
            pet_state=PetState(satiety=35, money=12),
            inventory={},
            auto_refill_enabled=True,
            auto_purchase_enabled=True,
        )
        window = self._window_like(save, FakeCarePlayback(PlaybackStartCheck(True)))

        changed = PetWindow._try_auto_refill_after_tick(window)

        self.assertTrue(changed)
        self.assertEqual(save.pet_state.money, 0)
        self.assertEqual(save.pet_state.satiety, 59)
        self.assertEqual(save.inventory, {})
        self.assertEqual(window._care_playback.started, ["simple_feed"])
        self.assertEqual(window._care_playback.started_items, ["rice_ball"])
        self.assertEqual(window.save_game_changed.emit_count, 1)
        self.assertIn("自动购买并使用了饭团", window._status_panel.notice)

    def test_auto_purchase_enabled_does_not_run_without_auto_refill(self) -> None:
        save = SaveGame(
            pet_state=PetState(satiety=35, money=20),
            inventory={},
            auto_refill_enabled=False,
            auto_purchase_enabled=True,
        )
        window = self._window_like(save, FakeCarePlayback(PlaybackStartCheck(True)))

        changed = PetWindow._try_auto_refill_after_tick(window)

        self.assertFalse(changed)
        self.assertEqual(save.pet_state.money, 20)
        self.assertEqual(save.pet_state.satiety, 35)
        self.assertEqual(save.inventory, {})
        self.assertEqual(window._status_panel.notices, [])
        self.assertEqual(window.save_game_changed.emit_count, 0)

    def test_auto_purchase_insufficient_money_does_not_buy_and_is_throttled(
        self,
    ) -> None:
        save = SaveGame(
            pet_state=PetState(satiety=35, money=2),
            inventory={},
            auto_refill_enabled=True,
            auto_purchase_enabled=True,
        )
        window = self._window_like(save, FakeCarePlayback(PlaybackStartCheck(True)))

        PetWindow._try_auto_refill_after_tick(window)
        PetWindow._try_auto_refill_after_tick(window)
        window._auto_refill_test_now = 901.0
        PetWindow._try_auto_refill_after_tick(window)

        self.assertEqual(save.pet_state.money, 2)
        self.assertEqual(save.inventory, {})
        self.assertEqual(window._care_playback.started, [])
        self.assertEqual(window.save_game_changed.emit_count, 0)
        self.assertEqual(len(window._status_panel.notices), 2)
        self.assertTrue(
            all("金币不足" in notice for notice in window._status_panel.notices)
        )
        self.assertEqual(
            window._auto_refill_missing_notice_shown_at,
            {"satiety:money": 901.0},
        )

    def test_auto_purchase_busy_playback_does_not_buy_or_notice(self) -> None:
        save = SaveGame(
            pet_state=PetState(satiety=35, money=20),
            inventory={},
            auto_refill_enabled=True,
            auto_purchase_enabled=True,
        )
        window = self._window_like(
            save,
            FakeCarePlayback(PlaybackStartCheck(False, "当前动作占用中，稍后再照顾。")),
        )

        changed = PetWindow._try_auto_refill_after_tick(window)

        self.assertFalse(changed)
        self.assertEqual(save.pet_state.money, 20)
        self.assertEqual(save.pet_state.satiety, 35)
        self.assertEqual(save.inventory, {})
        self.assertEqual(window._care_playback.started, [])
        self.assertEqual(window._status_panel.notices, [])
        self.assertEqual(window.save_game_changed.emit_count, 0)

    def test_auto_purchase_uses_at_most_one_purchased_item_per_tick(self) -> None:
        save = SaveGame(
            pet_state=PetState(satiety=25, health=20, money=100),
            inventory={},
            auto_refill_enabled=True,
            auto_purchase_enabled=True,
        )
        window = self._window_like(save, FakeCarePlayback(PlaybackStartCheck(True)))

        changed = PetWindow._try_auto_refill_after_tick(window)

        self.assertTrue(changed)
        self.assertEqual(save.pet_state.health, 42)
        self.assertEqual(save.pet_state.satiety, 25)
        self.assertEqual(save.pet_state.money, 76)
        self.assertEqual(save.inventory, {})
        self.assertEqual(window._care_playback.started, ["medicine"])
        self.assertEqual(window._care_playback.started_items, ["basic_medicine"])
        self.assertEqual(window.save_game_changed.emit_count, 1)

    def test_auto_purchase_keeps_item_if_unexpected_use_step_fails(self) -> None:
        class FlippingCarePlayback(FakeCarePlayback):
            def __init__(self) -> None:
                super().__init__(PlaybackStartCheck(True))
                self.checks = [
                    PlaybackStartCheck(True),
                    PlaybackStartCheck(False, "突然占用"),
                ]

            def can_start_care(self) -> PlaybackStartCheck:
                if self.checks:
                    return self.checks.pop(0)
                return PlaybackStartCheck(False, "突然占用")

        save = SaveGame(
            pet_state=PetState(satiety=35, money=12),
            inventory={},
            auto_refill_enabled=True,
            auto_purchase_enabled=True,
        )
        window = self._window_like(save, FlippingCarePlayback())

        changed = PetWindow._try_auto_refill_after_tick(window)

        self.assertTrue(changed)
        self.assertEqual(save.pet_state.money, 0)
        self.assertEqual(save.pet_state.satiety, 35)
        self.assertEqual(save.inventory, {"rice_ball": 1})
        self.assertEqual(window._care_playback.started, [])
        self.assertEqual(window.save_game_changed.emit_count, 1)
        self.assertIn("已留在背包", window._status_panel.notice)


class ShopInventoryWindowSmokeTest(unittest.TestCase):
    def _large_catalog(self, size: int = 180) -> ItemCatalog:
        base_items = list(load_item_catalog().items())
        items: list[ItemDefinition] = []
        for index in range(size):
            item = base_items[index % len(base_items)]
            items.append(
                ItemDefinition(
                    id=f"{item.id}_{index}",
                    name=f"{item.name}{index:03d}",
                    category=item.category,
                    price=item.price + index % 5,
                    effects=dict(item.effects),
                    description=item.description,
                    icon=item.icon,
                )
            )
        return ItemCatalog(items)

    def _wait_for_batches(self, app, window) -> None:
        from PyQt6.QtTest import QTest

        for _ in range(120):
            app.processEvents()
            if not window.has_pending_row_batches():
                return
            QTest.qWait(1)
        self.fail("商店/背包列表分批刷新没有在预期时间内完成")

    def _shop_row_ids(self, window) -> list[str]:
        from PyQt6.QtWidgets import QPushButton

        item_ids: list[str] = []
        for index in range(window._shop_list.count()):
            widget = window._shop_list.itemAt(index).widget()
            if widget is None or widget.objectName() != "itemRow":
                continue
            buttons = widget.findChildren(QPushButton)
            for button in buttons:
                name = button.objectName()
                if name.startswith("purchaseButton_"):
                    item_ids.append(name.removeprefix("purchaseButton_"))
        return item_ids

    def test_shop_window_offscreen_shows_catalog_context(self) -> None:
        from PyQt6.QtWidgets import QApplication, QLabel

        from ui.windows.shop_inventory_window import ShopInventoryWindow

        app = QApplication.instance() or QApplication([])
        window = ShopInventoryWindow()

        window.set_item_catalog(_catalog().items())
        window.set_pet_state(PetState(money=50))
        window.set_inventory({"rice_ball": 2})
        window.show_page("shop")
        app.processEvents()

        text = "\n".join(label.text() for label in window.findChildren(QLabel))
        self.assertIn("食物", text)
        self.assertIn("饭团", text)
        self.assertIn("小份主食，适合快速补充饱腹。", text)
        self.assertIn("12 金币", text)
        self.assertIn("饱腹 +24、心情 +2", text)
        self.assertIn("x2", text)
        icon_labels = window.findChildren(QLabel, "itemIconLabel")
        self.assertTrue(icon_labels)
        self.assertTrue(any(label.pixmap() is not None for label in icon_labels))
        self.assertTrue(all(label.width() == 48 for label in icon_labels))
        self.assertTrue(all(label.height() == 48 for label in icon_labels))

    def test_shop_default_sort_keeps_catalog_order(self) -> None:
        from PyQt6.QtWidgets import QApplication

        from ui.windows.shop_inventory_window import ShopInventoryWindow

        app = QApplication.instance() or QApplication([])
        window = ShopInventoryWindow()

        window.set_item_catalog(_catalog().items())
        window.show_page("shop")
        app.processEvents()

        self.assertEqual(
            self._shop_row_ids(window),
            [
                "rice_ball",
                "basic_medicine",
                "sparkling_water",
                "party_drink",
                "cleaning_wipes",
                "gift_box",
            ],
        )

    def test_shop_category_filter_refreshes_visible_items(self) -> None:
        from PyQt6.QtWidgets import QApplication, QComboBox

        from ui.windows.shop_inventory_window import ShopInventoryWindow

        app = QApplication.instance() or QApplication([])
        window = ShopInventoryWindow()

        window.set_item_catalog(_catalog().items())
        window.show_page("shop")
        category_combo = window.findChild(QComboBox, "shopCategoryCombo")
        self.assertIsNotNone(category_combo)
        category_combo.setCurrentText("饮料")
        app.processEvents()

        self.assertEqual(
            self._shop_row_ids(window),
            ["sparkling_water", "party_drink"],
        )

    def test_shop_price_sort_orders_low_to_high(self) -> None:
        from PyQt6.QtWidgets import QApplication, QComboBox

        from ui.windows.shop_inventory_window import ShopInventoryWindow

        app = QApplication.instance() or QApplication([])
        window = ShopInventoryWindow()

        window.set_item_catalog(_catalog().items())
        window.show_page("shop")
        sort_combo = window.findChild(QComboBox, "shopSortCombo")
        self.assertIsNotNone(sort_combo)
        sort_combo.setCurrentText("按价格排序")
        app.processEvents()

        self.assertEqual(
            self._shop_row_ids(window),
            [
                "sparkling_water",
                "rice_ball",
                "cleaning_wipes",
                "party_drink",
                "basic_medicine",
                "gift_box",
            ],
        )

    def test_shop_category_and_sort_stack(self) -> None:
        from PyQt6.QtWidgets import QApplication, QComboBox

        from ui.windows.shop_inventory_window import ShopInventoryWindow

        app = QApplication.instance() or QApplication([])
        window = ShopInventoryWindow()

        window.set_item_catalog(_catalog().items())
        window.show_page("shop")
        category_combo = window.findChild(QComboBox, "shopCategoryCombo")
        sort_combo = window.findChild(QComboBox, "shopSortCombo")
        self.assertIsNotNone(category_combo)
        self.assertIsNotNone(sort_combo)
        category_combo.setCurrentText("饮料")
        sort_combo.setCurrentText("按名称排序")
        app.processEvents()

        self.assertEqual(
            self._shop_row_ids(window),
            ["sparkling_water", "party_drink"],
        )

    def test_inventory_window_offscreen_shows_inventory_context(self) -> None:
        from PyQt6.QtWidgets import QApplication, QLabel

        from ui.windows.shop_inventory_window import ShopInventoryWindow

        app = QApplication.instance() or QApplication([])
        window = ShopInventoryWindow()

        window.set_item_catalog(_catalog().items())
        window.set_pet_state(PetState(satiety=40, money=50))
        window.set_inventory({"rice_ball": 1})
        window.show_page("inventory")
        app.processEvents()

        text = "\n".join(label.text() for label in window.findChildren(QLabel))
        self.assertIn("食物", text)
        self.assertIn("饭团", text)
        self.assertIn("x1", text)
        self.assertIn("饱腹 +24、心情 +2", text)
        icon_labels = window.findChildren(QLabel, "itemIconLabel")
        self.assertTrue(icon_labels)
        self.assertTrue(any(label.pixmap() is not None for label in icon_labels))
        self.assertTrue(all(label.width() == 48 for label in icon_labels))
        self.assertTrue(all(label.height() == 48 for label in icon_labels))

    def test_full_primary_status_disables_use_and_lower_status_restores_it(self) -> None:
        from PyQt6.QtWidgets import QApplication, QPushButton

        from ui.windows.shop_inventory_window import ShopInventoryWindow

        app = QApplication.instance() or QApplication([])
        window = ShopInventoryWindow()

        window.set_item_catalog(_catalog().items())
        window.set_pet_state(PetState(satiety=100, mood=40))
        window.set_inventory({"rice_ball": 1})
        window.show_page("inventory")
        app.processEvents()

        use_button = window.findChild(QPushButton, "useButton_rice_ball")
        self.assertIsNotNone(use_button)
        self.assertFalse(use_button.isEnabled())
        self.assertIn("饱腹已满", use_button.toolTip())

        window.set_pet_state(PetState(satiety=40, mood=40))
        app.processEvents()

        use_button = window.findChild(QPushButton, "useButton_rice_ball")
        self.assertIsNotNone(use_button)
        self.assertTrue(use_button.isEnabled())

    def test_shop_window_remembers_geometry_in_ui_settings(self) -> None:
        from PyQt6.QtWidgets import QApplication

        from ui.windows.shop_inventory_window import ShopInventoryWindow

        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as tmp_dir:
            settings_path = Path(tmp_dir) / "window_settings.json"
            settings_path.write_text("{}", encoding="utf-8")

            window = ShopInventoryWindow(geometry_settings_path=settings_path)
            window.show_page("shop")
            app.processEvents()
            window.resize(720, 500)
            window.move(80, 90)
            app.processEvents()
            saved_geometry = window.geometry()
            window.close()
            app.processEvents()

            payload = json.loads(settings_path.read_text(encoding="utf-8"))
            saved = payload["ui_windows"]["shop_inventory"]
            self.assertEqual(saved["width"], saved_geometry.width())
            self.assertEqual(saved["height"], saved_geometry.height())

            restored = ShopInventoryWindow(geometry_settings_path=settings_path)
            restored.show_page("inventory")
            app.processEvents()

            self.assertEqual(restored.width(), saved["width"])
            self.assertEqual(restored.height(), saved["height"])
            self.assertGreaterEqual(restored.x(), 0)
            self.assertGreaterEqual(restored.y(), 0)

    def test_item_icon_cache_reuses_scaled_pixmaps_after_refresh(self) -> None:
        from PyQt6.QtCore import QElapsedTimer
        from PyQt6.QtWidgets import QApplication

        from ui.windows.shop_inventory_window import (
            ShopInventoryWindow,
            clear_item_icon_cache,
            item_icon_cache_stats,
        )

        app = QApplication.instance() or QApplication([])
        clear_item_icon_cache()
        window = ShopInventoryWindow()
        window.set_item_catalog(_catalog().items())
        window.show_page("shop")
        app.processEvents()
        first_stats = item_icon_cache_stats()

        window._clear_row_caches()
        timer = QElapsedTimer()
        timer.start()
        window._rebuild_shop_page(reason="test")
        app.processEvents()
        second_refresh_ms = timer.nsecsElapsed() / 1_000_000
        second_stats = item_icon_cache_stats()

        self.assertLess(second_refresh_ms, SHOP_ICON_SECOND_REFRESH_LIMIT_MS)
        self.assertGreater(first_stats["pixmap_misses"], 0)
        self.assertEqual(second_stats["pixmap_misses"], first_stats["pixmap_misses"])
        self.assertGreater(second_stats["pixmap_hits"], first_stats["pixmap_hits"])

    def test_large_all_shop_refresh_is_split_into_small_batches(self) -> None:
        from PyQt6.QtCore import QElapsedTimer
        from PyQt6.QtWidgets import QApplication

        from core.performance import (
            clear_ui_perf_records,
            set_ui_perf_recording,
            ui_perf_records,
        )
        from ui.windows.shop_inventory_window import ShopInventoryWindow

        app = QApplication.instance() or QApplication([])
        set_ui_perf_recording(True)
        clear_ui_perf_records()
        try:
            window = ShopInventoryWindow()
            window.set_item_catalog(self._large_catalog(180).items())
            timer = QElapsedTimer()
            timer.start()
            window.show_page("shop")
            open_elapsed_ms = timer.nsecsElapsed() / 1_000_000
            self._wait_for_batches(app, window)
            records = ui_perf_records()
        finally:
            set_ui_perf_recording(False)

        batch_times = [
            record.elapsed_ms
            for record in records
            if record.name == "shop.append_row_batch"
        ]
        display_all_times = [
            record.elapsed_ms
            for record in records
            if record.name == "shop.display_all_items"
        ]
        self.assertLess(open_elapsed_ms, SHOP_LARGE_OPEN_LIMIT_MS)
        self.assertEqual(len(self._shop_row_ids(window)), 180)
        self.assertTrue(display_all_times)
        self.assertLess(max(display_all_times), SHOP_DISPLAY_ALL_LIMIT_MS)
        self.assertGreaterEqual(len(batch_times), 2)
        self.assertLess(max(batch_times), SHOP_ROW_BATCH_LIMIT_MS)


class StatusPanelSmokeTest(unittest.TestCase):
    def test_status_panel_feed_page_keeps_only_shop_inventory_entries(self) -> None:
        from PyQt6.QtWidgets import QApplication, QLabel, QPushButton

        from ui.panels.status_panel import PetStatusPanel

        app = QApplication.instance() or QApplication([])
        panel = PetStatusPanel()

        panel.set_item_catalog(_catalog().items())
        panel.set_inventory({"rice_ball": 2}, money=50)

        text = "\n".join(label.text() for label in panel.findChildren(QLabel))
        feed_buttons = {
            button.text()
            for button in panel._pages["feed"].findChildren(QPushButton)
        }
        self.assertIn("金币", text)
        self.assertIn("背包", text)
        self.assertEqual(feed_buttons, {"打开商店", "打开背包"})
        self.assertFalse(hasattr(panel, "care_action_requested"))
        self.assertNotIn("食物 · 饭团", text)
        self.assertNotIn("饱腹 +24、心情 +2", text)

    def test_status_panel_shop_inventory_buttons_emit_open_signals(self) -> None:
        from PyQt6.QtWidgets import QApplication, QPushButton

        from ui.panels.status_panel import PetStatusPanel

        app = QApplication.instance() or QApplication([])
        panel = PetStatusPanel()
        opened: list[str] = []

        panel.shop_requested.connect(lambda: opened.append("shop"))
        panel.inventory_requested.connect(lambda: opened.append("inventory"))

        buttons = {button.text(): button for button in panel.findChildren(QPushButton)}
        buttons["打开商店"].click()
        buttons["打开背包"].click()

        self.assertEqual(opened, ["shop", "inventory"])

    def test_status_panel_chat_button_emits_chat_request(self) -> None:
        from PyQt6.QtWidgets import QApplication, QPushButton

        from ui.panels.status_panel import PetStatusPanel

        app = QApplication.instance() or QApplication([])
        panel = PetStatusPanel()
        requested: list[str] = []

        panel.chat_requested.connect(lambda: requested.append("chat"))

        buttons = {button.text(): button for button in panel.findChildren(QPushButton)}
        buttons["和萝莉斯说话"].click()

        self.assertEqual(requested, ["chat"])

    def test_status_panel_auto_use_and_purchase_switch_labels(self) -> None:
        from PyQt6.QtWidgets import QApplication

        from ui.panels.status_panel import PetStatusPanel

        app = QApplication.instance() or QApplication([])
        panel = PetStatusPanel()

        panel.set_system_state(
            always_on_top=True,
            click_through=False,
            auto_move=False,
            dev_mode=False,
            status_decay_enabled=True,
            auto_refill_enabled=False,
            auto_purchase_enabled=True,
        )
        app.processEvents()

        self.assertEqual(panel._auto_refill_check.text(), "自动使用背包物品")
        self.assertEqual(panel._auto_purchase_check.text(), "缺货时自动购买")
        self.assertTrue(panel._auto_purchase_check.isChecked())
        self.assertFalse(panel._auto_purchase_check.isEnabled())

        panel.set_system_state(
            always_on_top=True,
            click_through=False,
            auto_move=False,
            dev_mode=False,
            status_decay_enabled=True,
            auto_refill_enabled=True,
            auto_purchase_enabled=True,
        )
        app.processEvents()

        self.assertTrue(panel._auto_purchase_check.isEnabled())

    def test_status_panel_compact_view_shows_chat_and_nav_only(self) -> None:
        from PyQt6.QtWidgets import QApplication

        from ui.panels.status_panel import PetStatusPanel

        app = QApplication.instance() or QApplication([])
        panel = PetStatusPanel()
        panel.show()
        panel.reset_view()
        app.processEvents()

        self.assertTrue(panel._chat_row.isVisible())
        self.assertFalse(panel._detail_frame.isVisible())
        self.assertEqual(set(panel._nav_buttons), {"feed", "stats", "activity", "custom", "system"})

    def test_status_panel_hover_expands_and_switches_sections(self) -> None:
        from PyQt6.QtCore import QEvent
        from PyQt6.QtWidgets import QApplication

        from ui.panels.status_panel import PetStatusPanel

        app = QApplication.instance() or QApplication([])
        panel = PetStatusPanel()
        panel.show()
        panel.reset_view()
        app.processEvents()

        QApplication.sendEvent(panel._nav_buttons["feed"], QEvent(QEvent.Type.Enter))
        app.processEvents()
        self.assertEqual(panel._active_section, "feed")
        self.assertTrue(panel._detail_frame.isVisible())
        self.assertFalse(panel._chat_row.isVisible())
        self.assertTrue(panel._nav_buttons["feed"].isChecked())

        QApplication.sendEvent(panel._nav_buttons["stats"], QEvent(QEvent.Type.Enter))
        app.processEvents()
        self.assertEqual(panel._active_section, "stats")
        self.assertTrue(panel._nav_buttons["stats"].isChecked())
        self.assertFalse(panel._nav_buttons["feed"].isChecked())

    def test_status_panel_hover_does_not_open_or_sync_large_windows(self) -> None:
        from PyQt6.QtCore import QElapsedTimer, QEvent
        from PyQt6.QtWidgets import QApplication

        from ui.panels.status_panel import PetStatusPanel

        app = QApplication.instance() or QApplication([])
        panel = PetStatusPanel()
        opened: list[str] = []
        panel.shop_requested.connect(lambda: opened.append("shop"))
        panel.inventory_requested.connect(lambda: opened.append("inventory"))
        panel.activity_window_requested.connect(lambda: opened.append("activity"))
        panel.show()
        panel.reset_view()
        app.processEvents()

        timer = QElapsedTimer()
        timer.start()
        for key in ("feed", "activity", "stats", "custom", "system"):
            QApplication.sendEvent(panel._nav_buttons[key], QEvent(QEvent.Type.Enter))
            app.processEvents()
        hover_ms = timer.nsecsElapsed() / 1_000_000

        self.assertLess(hover_ms, STATUS_PANEL_HOVER_LIMIT_MS)
        self.assertEqual(opened, [])
        self.assertEqual(panel._active_section, "system")

    def test_status_panel_leave_delay_closes_and_reenter_cancels(self) -> None:
        from PyQt6.QtCore import QEvent
        from PyQt6.QtTest import QTest
        from PyQt6.QtWidgets import QApplication

        from ui.panels.status_panel import PetStatusPanel

        app = QApplication.instance() or QApplication([])
        panel = PetStatusPanel()
        panel.show()
        panel._show_section("feed")
        app.processEvents()

        QApplication.sendEvent(panel, QEvent(QEvent.Type.Leave))
        QTest.qWait(80)
        QApplication.sendEvent(panel, QEvent(QEvent.Type.Enter))
        QTest.qWait(240)
        app.processEvents()
        self.assertTrue(panel.isVisible())

        QApplication.sendEvent(panel, QEvent(QEvent.Type.Leave))
        QTest.qWait(240)
        app.processEvents()
        self.assertFalse(panel.isVisible())

    def test_status_panel_activity_page_is_slim_entry_surface(self) -> None:
        from PyQt6.QtWidgets import QApplication, QComboBox, QLabel, QPushButton

        from ui.panels.status_panel import PetStatusPanel

        app = QApplication.instance() or QApplication([])
        panel = PetStatusPanel()
        panel.set_pet_state(PetState(energy=80, mood=80, health=80))
        panel.set_activity_snapshot(
            ActivitySnapshot(
                is_active=True,
                activity_id="work_cleaning",
                name="打扫委托",
                category="工作",
                elapsed_seconds=60,
                duration_seconds=900,
            ),
            can_start=True,
        )
        panel._show_section("activity")
        app.processEvents()

        buttons = {
            button.text()
            for button in panel._pages["activity"].findChildren(QPushButton)
        }
        detail_text = "\n".join(
            label.text()
            for label in panel._pages["activity"].findChildren(QLabel)
        )

        self.assertEqual(buttons, {"取消活动", "活动详情"})
        self.assertIn("打扫委托", detail_text)
        self.assertEqual(panel._pages["activity"].findChildren(QComboBox), [])

    def test_status_panel_custom_page_exposes_runtime_plugin_controls(self) -> None:
        from PyQt6.QtWidgets import QApplication

        from ui.panels.status_panel import PetStatusPanel

        app = QApplication.instance() or QApplication([])
        panel = PetStatusPanel()
        toggled: list[tuple[str, bool]] = []
        tomato_toggles: list[bool] = []
        panel.plugin_toggled.connect(
            lambda plugin_id, enabled: toggled.append((plugin_id, bool(enabled)))
        )
        panel.tomato_clock_toggled.connect(
            lambda enabled: tomato_toggles.append(bool(enabled))
        )

        panel.set_plugin_toggles((("show_sticker", "发表情", True),))
        panel.set_tomato_clock_state(available=True, running=False)
        panel._show_section("custom")
        app.processEvents()

        plugin_check = panel._plugin_toggle_checks["show_sticker"]
        tomato_check = panel._tomato_clock_check
        self.assertTrue(plugin_check.isChecked())
        self.assertTrue(tomato_check.isEnabled())
        self.assertFalse(tomato_check.isChecked())

        plugin_check.click()
        tomato_check.click()
        app.processEvents()

        self.assertEqual(toggled, [("show_sticker", False)])
        self.assertEqual(tomato_toggles, [True])


class ActivityWindowSmokeTest(unittest.TestCase):
    def _window(self):
        from PyQt6.QtWidgets import QApplication

        from ui.windows.activity_window import ActivityWindow

        app = QApplication.instance() or QApplication([])
        window = ActivityWindow()
        window.set_activities(load_activity_catalog().activities())
        return app, window

    def test_activity_window_offscreen_hosts_activity_selector(self) -> None:
        from PyQt6.QtWidgets import QComboBox, QPushButton

        app, window = self._window()
        window.set_pet_state(PetState(energy=80, mood=80, health=80))
        window.show_window()
        app.processEvents()

        category_combo = window.findChild(QComboBox, "activityCategoryCombo")
        activity_combo = window.findChild(QComboBox, "activitySelectCombo")
        start_button = window.findChild(QPushButton, "activityStartButton")

        self.assertIsNotNone(category_combo)
        self.assertIsNotNone(activity_combo)
        self.assertIsNotNone(start_button)
        self.assertEqual(
            [category_combo.itemText(index) for index in range(category_combo.count())],
            ["工作", "学习", "运动", "休息", "日常互动"],
        )
        self.assertIn("擦擦屏幕x", activity_combo.currentText())
        self.assertTrue(start_button.isEnabled())
        self.assertEqual(start_button.text(), "开始活动")

    def test_activity_window_refreshes_details_for_each_category(self) -> None:
        from PyQt6.QtWidgets import QComboBox, QLabel

        app, window = self._window()
        window.set_pet_state(PetState(energy=80, mood=80, health=80))
        window.show_window()
        app.processEvents()

        category_combo = window.findChild(QComboBox, "activityCategoryCombo")
        activity_combo = window.findChild(QComboBox, "activitySelectCombo")
        expected = {
            "工作": ("擦擦屏幕x", "金币 +30"),
            "学习": ("看小红书", "经验 +26"),
            "运动": ("跳绳", "心情 +18"),
            "休息": ("眠眠", "体力 +16"),
            "日常互动": ("摸摸头", "亲密度 +1"),
        }

        for category, (activity_name, detail_fragment) in expected.items():
            with self.subTest(category=category):
                category_combo.setCurrentText(category)
                app.processEvents()
                detail_text = "\n".join(label.text() for label in window.findChildren(QLabel))
                self.assertEqual(activity_combo.currentText(), activity_name)
                self.assertIn(detail_fragment, detail_text)

    def test_activity_window_disables_start_when_status_is_insufficient(self) -> None:
        from PyQt6.QtWidgets import QPushButton

        app, window = self._window()
        window.set_pet_state(PetState(energy=5, mood=80, health=80))
        window.show_window()
        app.processEvents()

        start_button = window.findChild(QPushButton, "activityStartButton")

        self.assertFalse(start_button.isEnabled())
        self.assertEqual(start_button.text(), "状态不足")
        self.assertIn("状态不足：体力 5/30", start_button.toolTip())

    def test_activity_window_disables_start_while_activity_is_active(self) -> None:
        from PyQt6.QtWidgets import QPushButton

        app, window = self._window()
        window.set_pet_state(PetState(energy=80, mood=80, health=80))
        window.set_activity_snapshot(
            ActivitySnapshot(
                is_active=True,
                activity_id="work_cleaning",
                name="打扫委托",
                category="工作",
                elapsed_seconds=60,
                duration_seconds=900,
            ),
            can_start=True,
        )
        window.show_window()
        app.processEvents()

        start_button = window.findChild(QPushButton, "activityStartButton")

        self.assertFalse(start_button.isEnabled())
        self.assertEqual(start_button.text(), "活动进行中")
        self.assertIn("活动进行中", start_button.toolTip())

    def test_activity_window_remembers_geometry_in_ui_settings(self) -> None:
        from PyQt6.QtWidgets import QApplication

        from ui.windows.activity_window import ActivityWindow

        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as tmp_dir:
            settings_path = Path(tmp_dir) / "window_settings.json"
            settings_path.write_text("{}", encoding="utf-8")
            window = ActivityWindow(geometry_settings_path=settings_path)
            window.show_window()
            app.processEvents()
            window.resize(520, 460)
            window.move(70, 80)
            app.processEvents()
            saved_geometry = window.geometry()
            window.close()
            app.processEvents()

            saved = json.loads(settings_path.read_text(encoding="utf-8"))["ui_windows"][
                "activity"
            ]
            self.assertEqual(saved["width"], saved_geometry.width())
            self.assertEqual(saved["height"], saved_geometry.height())

            restored = ActivityWindow(geometry_settings_path=settings_path)
            restored.show_window()
            app.processEvents()

            self.assertEqual(restored.width(), saved["width"])
            self.assertEqual(restored.height(), saved["height"])


class PetWindowPluginControlsSmokeTest(unittest.TestCase):
    def _window_like(self):
        window = type("WindowLike", (), {})()
        window._status_panel = FakeCustomStatusPanel()
        window._plugins = [FakeRuntimePlugin(), FakeTomatoClockPlugin()]
        return window

    def test_sync_custom_panel_reports_runtime_plugin_and_tomato_state(self) -> None:
        window = self._window_like()

        PetWindow._sync_custom_panel(window)

        self.assertEqual(
            window._status_panel.plugin_toggles[-1],
            (("show_sticker", "发表情", True),),
        )
        self.assertEqual(
            window._status_panel.tomato_states[-1],
            {"available": True, "running": False, "paused": False},
        )

    def test_runtime_plugin_toggle_calls_plugin_set_enabled(self) -> None:
        window = self._window_like()
        plugin = window._plugins[0]

        PetWindow._set_runtime_plugin_enabled(window, "show_sticker", False)

        self.assertFalse(plugin.enabled)
        self.assertEqual(plugin.set_calls, [False])
        self.assertEqual(
            window._status_panel.plugin_toggles[-1],
            (("show_sticker", "发表情", False),),
        )

    def test_tomato_clock_toggle_calls_running_control(self) -> None:
        window = self._window_like()
        tomato = window._plugins[1]

        PetWindow._set_tomato_clock_running(window, True)

        self.assertTrue(tomato.running)
        self.assertEqual(tomato.set_calls, [True])
        self.assertEqual(
            window._status_panel.tomato_states[-1],
            {"available": True, "running": True, "paused": False},
        )


class PetWindowChatEntrySmokeTest(unittest.TestCase):
    def test_open_chat_window_lazily_creates_controller_and_uses_display_rect(self) -> None:
        from unittest.mock import patch

        from PyQt6.QtWidgets import QApplication, QLabel, QWidget

        app = QApplication.instance() or QApplication([])
        host = QWidget()
        host.move(120, 90)
        label = QLabel(host)
        label.setGeometry(8, 12, 96, 80)
        host.show()
        app.processEvents()

        created: list[object] = []

        class FakeChatController:
            def __init__(
                self,
                *,
                parent,
                rect_provider,
                effect_executor=None,
                pet_context_provider=None,
            ):
                self.parent = parent
                self.rect_provider = rect_provider
                self.effect_executor = effect_executor
                self.pet_context_provider = pet_context_provider
                self.show_count = 0
                self.reposition_count = 0
                created.append(self)

            def show_window(self) -> None:
                self.show_count += 1

            def reposition_window(self) -> bool:
                self.reposition_count += 1
                return True

        window = type("WindowLike", (), {})()
        window._label = label
        window._chat_controller = None
        window._chat_effect_executor = object()
        window._chat_context_provider = object()
        window.get_pet_display_global_rect = (
            lambda: PetWindow.get_pet_display_global_rect(window)
        )
        window.ensure_chat_controller = lambda: PetWindow.ensure_chat_controller(window)

        with patch("ui.pet_window.ChatController", FakeChatController):
            PetWindow.open_chat_window(window)
            PetWindow.open_chat_window(window)
            PetWindow.reposition_chat_window(window)
            rect = created[0].rect_provider()

        self.assertEqual(len(created), 1)
        self.assertEqual(created[0].parent, window)
        self.assertIs(created[0].effect_executor, window._chat_effect_executor)
        self.assertIs(created[0].pet_context_provider, window._chat_context_provider)
        self.assertEqual(created[0].show_count, 2)
        self.assertEqual(created[0].reposition_count, 1)
        self.assertEqual(rect, PetWindow.get_pet_display_global_rect(window))
        self.assertEqual(rect.size(), label.rect().size())
        host.hide()

    def test_context_menu_closes_visible_chat_before_showing_status_panel(self) -> None:
        class FakeEvent:
            def __init__(self) -> None:
                self.accepted = False

            def accept(self) -> None:
                self.accepted = True

        class FakeChatWindow:
            def __init__(self) -> None:
                self.visible = True

            def isVisible(self) -> bool:
                return self.visible

        class FakeChatController:
            def __init__(self) -> None:
                self.window = FakeChatWindow()
                self.hide_count = 0

            def hide_window(self) -> None:
                self.hide_count += 1
                self.window.visible = False

        toggles: list[str] = []
        controller = FakeChatController()
        window = type("WindowLike", (), {})()
        window._chat_controller = controller
        window._interaction_end_locked = lambda: False
        window.toggle_status_panel = lambda: toggles.append("status")

        first_event = FakeEvent()
        PetWindow.contextMenuEvent(window, first_event)
        second_event = FakeEvent()
        PetWindow.contextMenuEvent(window, second_event)

        self.assertTrue(first_event.accepted)
        self.assertEqual(controller.hide_count, 1)
        self.assertEqual(toggles, ["status"])
        self.assertTrue(second_event.accepted)

    def test_context_menu_after_outside_closed_chat_shows_status_panel(self) -> None:
        class FakeEvent:
            def __init__(self) -> None:
                self.accepted = False

            def accept(self) -> None:
                self.accepted = True

        class FakeChatWindow:
            def __init__(self) -> None:
                self.visible = True
                self.closed_by_outside = True

            def isVisible(self) -> bool:
                return self.visible

            def take_closed_by_outside(self) -> bool:
                was_closed = self.closed_by_outside
                self.closed_by_outside = False
                return was_closed

        class FakeChatController:
            def __init__(self) -> None:
                self.window = FakeChatWindow()
                self.hide_count = 0

            def hide_window(self) -> None:
                self.hide_count += 1
                self.window.visible = False

        toggles: list[str] = []
        controller = FakeChatController()
        window = type("WindowLike", (), {})()
        window._chat_controller = controller
        window._interaction_end_locked = lambda: False
        window.toggle_status_panel = lambda: toggles.append("status")

        event = FakeEvent()
        PetWindow.contextMenuEvent(window, event)

        self.assertTrue(event.accepted)
        self.assertEqual(controller.hide_count, 1)
        self.assertEqual(toggles, ["status"])


class PetWindowShopInventorySyncSmokeTest(unittest.TestCase):
    def _window_like(self, save: SaveGame):
        window = type("WindowLike", (), {})()
        window._save_game = save
        window._item_catalog = _catalog()
        window._status_panel = FakeStatusPanel()
        window._shop_inventory_window = FakeShopInventoryWindow()
        window._director = FakeDirector()
        window._care_playback = FakeCarePlayback(PlaybackStartCheck(True))
        window._status_ticker = FakeTicker()
        window.save_game_changed = FakeSignal()
        window._sync_shop_inventory_window = (
            lambda: PetWindow._sync_shop_inventory_window(window)
        )
        window._sync_status_panel_info = lambda: PetWindow._sync_status_panel_info(window)
        window._sync_inventory_panel = lambda: PetWindow._sync_inventory_panel(window)
        return window

    def test_hidden_shop_inventory_sync_marks_dirty_without_refreshing_lists(self) -> None:
        from PyQt6.QtCore import QElapsedTimer

        save = SaveGame(pet_state=PetState(money=20), inventory={"rice_ball": 1})
        window = self._window_like(save)
        hidden_window = HiddenFakeShopInventoryWindow()
        window._shop_inventory_window = hidden_window

        timer = QElapsedTimer()
        timer.start()
        PetWindow._sync_shop_inventory_window(window)
        hidden_ms = timer.nsecsElapsed() / 1_000_000

        self.assertLess(hidden_ms, SHOP_HIDDEN_SYNC_LIMIT_MS)
        self.assertEqual(hidden_window.dirty_count, 1)
        self.assertEqual(hidden_window.inventory_calls, [])
        self.assertEqual(hidden_window.pet_state_money, [])

        PetWindow._sync_shop_inventory_window(window, force=True)

        self.assertEqual(hidden_window.inventory_calls, [{"rice_ball": 1}])
        self.assertEqual(hidden_window.pet_state_money, [20])

    def test_purchase_refreshes_shop_inventory_and_status_panel(self) -> None:
        save = SaveGame(pet_state=PetState(money=20))
        window = self._window_like(save)

        PetWindow._purchase_item(window, "rice_ball")

        self.assertEqual(save.pet_state.money, 8)
        self.assertEqual(save.inventory, {"rice_ball": 1})
        self.assertEqual(window.save_game_changed.emit_count, 1)
        self.assertIn("已购买：饭团", window._status_panel.notice)
        self.assertIn("已购买：饭团", window._shop_inventory_window.notices[-1])
        self.assertIn(({"rice_ball": 1}, 8), window._status_panel.inventory_calls)
        self.assertIn({"rice_ball": 1}, window._shop_inventory_window.inventory_calls)
        self.assertIn(8, window._status_panel.pet_state_money)
        self.assertIn(8, window._shop_inventory_window.pet_state_money)

    def test_insufficient_money_purchase_reports_in_both_surfaces(self) -> None:
        save = SaveGame(pet_state=PetState(money=2))
        window = self._window_like(save)

        PetWindow._purchase_item(window, "rice_ball")

        self.assertEqual(save.pet_state.money, 2)
        self.assertEqual(save.inventory, {})
        self.assertEqual(window.save_game_changed.emit_count, 0)
        self.assertIn("金币不足", window._status_panel.notice)
        self.assertIn("金币不足", window._shop_inventory_window.notices[-1])

    def test_missing_quantity_use_reports_in_both_surfaces_without_deducting(self) -> None:
        save = SaveGame(pet_state=PetState(satiety=40), inventory={})
        window = self._window_like(save)

        PetWindow._use_item(window, "rice_ball")

        self.assertEqual(save.pet_state.satiety, 40)
        self.assertEqual(save.inventory, {})
        self.assertEqual(window._status_ticker.reset_count, 0)
        self.assertEqual(window.save_game_changed.emit_count, 0)
        self.assertIn("背包里没有", window._status_panel.notice)
        self.assertIn("背包里没有", window._shop_inventory_window.notices[-1])

    def test_full_status_use_reports_in_both_surfaces_without_deducting(self) -> None:
        save = SaveGame(
            pet_state=PetState(satiety=100, mood=40),
            inventory={"rice_ball": 1},
        )
        window = self._window_like(save)

        PetWindow._use_item(window, "rice_ball")

        self.assertEqual(save.pet_state.satiety, 100)
        self.assertEqual(save.inventory, {"rice_ball": 1})
        self.assertEqual(window._status_ticker.reset_count, 0)
        self.assertEqual(window.save_game_changed.emit_count, 0)
        self.assertIn("用不上", window._status_panel.notice)
        self.assertIn("用不上", window._shop_inventory_window.notices[-1])

    def test_purchase_and_use_update_visible_shop_without_full_rebuild_cost(self) -> None:
        from PyQt6.QtCore import QElapsedTimer
        from PyQt6.QtTest import QTest
        from PyQt6.QtWidgets import QApplication

        from core.performance import (
            clear_ui_perf_records,
            set_ui_perf_recording,
            ui_perf_records,
        )
        from ui.windows.shop_inventory_window import ShopInventoryWindow

        app = QApplication.instance() or QApplication([])
        catalog = ShopInventoryWindowSmokeTest()._large_catalog(180)
        save = SaveGame(
            pet_state=PetState(
                money=9999,
                satiety=30,
                energy=30,
                health=30,
                cleanliness=30,
            ),
            inventory={item.id: 2 for item in catalog.items()[:90]},
        )
        window = self._window_like(save)
        real_shop = ShopInventoryWindow()
        real_shop.set_item_catalog(catalog.items())
        real_shop.set_pet_state(save.pet_state)
        real_shop.set_inventory(save.inventory)
        real_shop.show_page("shop")
        for _ in range(120):
            app.processEvents()
            if not real_shop.has_pending_row_batches():
                break
            QTest.qWait(1)
        window._item_catalog = catalog
        window._shop_inventory_window = real_shop
        window._sync_shop_inventory_window = (
            lambda **kwargs: PetWindow._sync_shop_inventory_window(window, **kwargs)
        )
        window._request_visual_state_update = lambda: None
        window._refresh_dev_debug = lambda: None
        item_id = catalog.items()[0].id

        set_ui_perf_recording(True)
        clear_ui_perf_records()
        timer = QElapsedTimer()
        try:
            timer.start()
            PetWindow._purchase_item(window, item_id)
            app.processEvents()
            purchase_ms = timer.nsecsElapsed() / 1_000_000
            purchase_records = ui_perf_records()

            clear_ui_perf_records()
            timer.restart()
            PetWindow._use_item(window, item_id)
            app.processEvents()
            use_ms = timer.nsecsElapsed() / 1_000_000
            use_records = ui_perf_records()
        finally:
            set_ui_perf_recording(False)

        purchase_record_names = {record.name for record in purchase_records}
        use_record_names = {record.name for record in use_records}
        self.assertLess(purchase_ms, SHOP_VISIBLE_ACTION_LIMIT_MS)
        self.assertLess(use_ms, SHOP_VISIBLE_ACTION_LIMIT_MS)
        self.assertNotIn("shop.refresh_list", purchase_record_names)
        self.assertNotIn("inventory.refresh_list", purchase_record_names)
        self.assertNotIn("shop.refresh_list", use_record_names)
        self.assertNotIn("inventory.refresh_list", use_record_names)


if __name__ == "__main__":
    unittest.main()
