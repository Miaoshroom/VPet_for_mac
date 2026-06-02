"""桌宠养成会话协调"""

from __future__ import annotations

from time import monotonic

from core.performance import measure_ui
from core.raising.auto_refill import (
    AUTO_REFILL_RULES,
    AutoRefillDecision,
    AutoRefillField,
    choose_auto_purchase_item,
    evaluate_auto_refill,
)
from core.raising.items import (
    purchase_item as apply_item_purchase,
    use_inventory_item,
)
from core.raising.leveling import format_level_up_notice
from core.raising.notices import (
    auto_purchase_insufficient_money_notice,
    auto_refill_missing_notice,
    care_action_for_item_category,
    format_item_deltas,
    join_notice,
)
from core.raising.status_ticker import DEFAULT_TICK_SECONDS

AUTO_REFILL_MISSING_NOTICE_SECONDS = 15 * 60


def advance_pet_status(self) -> None:
    status_result = self._status_ticker.advance(
        enabled=self._save_game.status_decay_enabled,
    )
    activity_result = self._activity_system.advance(DEFAULT_TICK_SECONDS)
    if activity_result.settlement is not None:
        self._status_ticker.reset()
        self._activity_playback.finish_activity_animation()
        level_notice = show_level_notice(self, activity_result.settlement.level_result)
        show_activity_notice(
            self,
            join_notice(activity_result.message, level_notice),
        )
        self._request_visual_state_update()
    elif status_result.changed:
        self._request_visual_state_update()
    auto_refill_changed = try_auto_refill_after_tick(self)
    if (
        not status_result.changed
        and not activity_result.changed
        and not auto_refill_changed
    ):
        return
    self._sync_status_panel_info()
    self._sync_activity_panel()
    if not auto_refill_changed:
        self.save_game_changed.emit()


def purchase_item(self, item_id: str) -> None:
    with measure_ui("shop.click_purchase", detail=item_id):
        result = apply_item_purchase(
            state=self._save_game.pet_state,
            inventory=self._save_game.inventory,
            catalog=self._item_catalog,
            item_id=item_id,
        )
        show_item_notice(self, result.message, include_item_window=True)
        self._sync_status_panel_info()
        self._sync_inventory_panel()
        if result.changed:
            self.save_game_changed.emit()


def use_item(self, item_id: str) -> None:
    use_inventory_item_for_care(self, item_id, auto=False)


def try_auto_refill_after_tick(self) -> bool:
    if not self._save_game.auto_refill_enabled:
        return False
    clear_resolved_auto_refill_missing_notices(self)
    decision = evaluate_auto_refill(
        state=self._save_game.pet_state,
        inventory=self._save_game.inventory,
        catalog=self._item_catalog,
    )
    if decision.kind == "not_triggered":
        return False
    if decision.kind == "missing_stock":
        if self._save_game.auto_purchase_enabled:
            return try_auto_purchase_and_use(self, decision)
        show_auto_refill_missing_notice(self, decision)
        return False
    if decision.rule is None or decision.item is None:
        return False
    changed = use_inventory_item_for_care(
        self,
        decision.item.id,
        auto=True,
    )
    if changed:
        clear_auto_refill_missing_notice(self, decision.rule.field)
    return changed


def try_auto_purchase_and_use(
    self,
    decision: AutoRefillDecision,
) -> bool:
    if decision.rule is None:
        return False

    check = self._care_playback.can_start_care()
    if not check.ok:
        return False

    purchase_decision = choose_auto_purchase_item(
        state=self._save_game.pet_state,
        catalog=self._item_catalog,
        rule=decision.rule,
        money=self._save_game.pet_state.money,
    )
    if purchase_decision.kind == "not_found":
        show_auto_refill_missing_notice(self, decision)
        return False
    if purchase_decision.kind == "insufficient_money":
        show_auto_purchase_insufficient_money_notice(self, purchase_decision)
        return False
    if purchase_decision.item is None:
        return False

    purchase = apply_item_purchase(
        state=self._save_game.pet_state,
        inventory=self._save_game.inventory,
        catalog=self._item_catalog,
        item_id=purchase_decision.item.id,
    )
    if not purchase.ok:
        show_auto_purchase_insufficient_money_notice(self, purchase_decision)
        return False

    used = use_inventory_item_for_care(
        self,
        purchase_decision.item.id,
        auto=True,
        auto_purchase=True,
    )
    if used:
        clear_auto_refill_missing_notice(self, decision.rule.field)
        return True

    show_item_notice(
        self,
        f"已自动购买{purchase_decision.item.name}，但暂时没有用掉，已留在背包。",
        include_item_window=False,
    )
    self._sync_status_panel_info()
    self._sync_inventory_panel()
    self.save_game_changed.emit()
    return True


def auto_refill_missing_notice_state(self) -> dict[str, float]:
    notices = getattr(self, "_auto_refill_missing_notice_shown_at", None)
    if notices is None:
        notices = {}
        self._auto_refill_missing_notice_shown_at = notices
    return notices


def clear_auto_refill_missing_notice(self, field: AutoRefillField) -> None:
    notices = auto_refill_missing_notice_state(self)
    notices.pop(field, None)
    notices.pop(_auto_purchase_money_notice_key(field), None)


def clear_all_auto_refill_missing_notices(self) -> None:
    auto_refill_missing_notice_state(self).clear()


def clear_resolved_auto_refill_missing_notices(self) -> None:
    notices = auto_refill_missing_notice_state(self)
    for rule in AUTO_REFILL_RULES:
        if int(getattr(self._save_game.pet_state, rule.field)) > rule.threshold:
            notices.pop(rule.field, None)
            notices.pop(_auto_purchase_money_notice_key(rule.field), None)


def show_auto_refill_missing_notice(
    self,
    decision: AutoRefillDecision,
) -> None:
    if decision.rule is None:
        return
    notices = auto_refill_missing_notice_state(self)
    field = decision.rule.field
    clock = getattr(self, "_auto_refill_notice_clock", monotonic)
    now = float(clock())
    interval_seconds = float(
        getattr(
            self,
            "_auto_refill_missing_notice_interval_seconds",
            AUTO_REFILL_MISSING_NOTICE_SECONDS,
        )
    )
    last_shown_at = notices.get(field)
    if last_shown_at is not None and now - last_shown_at < interval_seconds:
        return
    notices[field] = now
    self._status_panel.set_care_notice(auto_refill_missing_notice(decision.rule))


def show_auto_purchase_insufficient_money_notice(
    self,
    decision,
) -> None:
    if decision.rule is None or decision.item is None:
        return
    key = _auto_purchase_money_notice_key(decision.rule.field)
    notices = auto_refill_missing_notice_state(self)
    clock = getattr(self, "_auto_refill_notice_clock", monotonic)
    now = float(clock())
    interval_seconds = float(
        getattr(
            self,
            "_auto_refill_missing_notice_interval_seconds",
            AUTO_REFILL_MISSING_NOTICE_SECONDS,
        )
    )
    last_shown_at = notices.get(key)
    if last_shown_at is not None and now - last_shown_at < interval_seconds:
        return
    notices[key] = now
    self._status_panel.set_care_notice(
        auto_purchase_insufficient_money_notice(
            decision.rule,
            decision.item.name,
            decision.item.price,
        )
    )


def _auto_purchase_money_notice_key(field: AutoRefillField) -> str:
    return f"{field}:money"


def use_inventory_item_for_care(
    self,
    item_id: str,
    *,
    auto: bool,
    auto_purchase: bool = False,
) -> bool:
    perf_name = "shop.click_use" if not auto else "shop.auto_use"
    with measure_ui(perf_name, detail=item_id):
        check = self._care_playback.can_start_care()
        if not check.ok:
            if not auto:
                show_item_notice(self, check.message, include_item_window=True)
                sync_shop_inventory_window_if_present(self)
            return False

        result = use_inventory_item(
            state=self._save_game.pet_state,
            inventory=self._save_game.inventory,
            catalog=self._item_catalog,
            item_id=item_id,
        )
        if not result.ok:
            if not auto:
                show_item_notice(self, result.message, include_item_window=True)
            self._sync_inventory_panel()
            return False
        if result.item is None:
            if not auto:
                show_item_notice(self, result.message, include_item_window=True)
            return False

        self._status_ticker.reset()
        care_action_id = care_action_for_item_category(result.item.category)
        playback = self._care_playback.start_care_animation(care_action_id)
        self._request_visual_state_update()
        self._sync_status_panel_info()
        self._sync_inventory_panel()
        if auto_purchase:
            success_message = f"自动购买并使用了{result.item.name}"
        elif auto:
            success_message = f"自动使用了{result.item.name}"
        else:
            success_message = result.message
        notice = join_notice(
            success_message,
            format_item_deltas(result.deltas or {}),
            playback.message,
        )
        show_item_notice(self, notice, include_item_window=not auto)
        self.save_game_changed.emit()
        return True


def start_activity(self, activity_id: str) -> None:
    if not self._activity_system.is_active():
        check = self._activity_playback.can_start_activity()
        if not check.ok:
            show_activity_notice(self, check.message)
            return
    result = self._activity_system.start(activity_id)
    message = result.message
    if result.ok and result.activity is not None:
        playback = self._activity_playback.start_activity_animation(result.activity)
        message = join_notice(message, playback.message)
        self._request_visual_state_update()
    show_activity_notice(self, message)
    self._sync_status_panel_info()
    self._sync_activity_panel()
    if result.changed:
        self.save_game_changed.emit()


def cancel_activity(self) -> None:
    result = self._activity_system.cancel()
    level_notice = ""
    if result.settlement is not None:
        self._status_ticker.reset()
        self._activity_playback.finish_activity_animation()
        level_notice = show_level_notice(self, result.settlement.level_result)
        self._request_visual_state_update()
    show_activity_notice(self, join_notice(result.message, level_notice))
    self._sync_status_panel_info()
    self._sync_activity_panel()
    if result.changed:
        self.save_game_changed.emit()


def set_status_decay_enabled(self, enabled: bool) -> None:
    enabled = bool(enabled)
    if self._save_game.status_decay_enabled == enabled:
        return
    self._save_game.status_decay_enabled = enabled
    self._status_ticker.reset()
    self._sync_status_panel_controls()
    self.save_game_changed.emit()


def set_auto_refill_enabled(self, enabled: bool) -> None:
    enabled = bool(enabled)
    if self._save_game.auto_refill_enabled == enabled:
        return
    self._save_game.auto_refill_enabled = enabled
    if not enabled:
        clear_all_auto_refill_missing_notices(self)
    self._sync_status_panel_controls()
    self.save_game_changed.emit()


def set_auto_purchase_enabled(self, enabled: bool) -> None:
    enabled = bool(enabled)
    if self._save_game.auto_purchase_enabled == enabled:
        return
    self._save_game.auto_purchase_enabled = enabled
    if not enabled:
        clear_all_auto_refill_missing_notices(self)
    self._sync_status_panel_controls()
    self.save_game_changed.emit()


def show_item_notice(
    self,
    message: str,
    *,
    include_item_window: bool,
) -> None:
    self._status_panel.set_care_notice(message)
    if include_item_window and hasattr(self, "_shop_inventory_window"):
        self._shop_inventory_window.set_notice(message)


def show_activity_notice(self, message: str) -> None:
    self._status_panel.set_activity_notice(message)
    if hasattr(self, "_activity_window"):
        self._activity_window.set_activity_notice(message)


def show_level_notice(self, level_result) -> str:
    notice = format_level_up_notice(level_result)
    if notice:
        self._status_panel.set_level_notice(notice)
    return notice


def sync_shop_inventory_window_if_present(self) -> None:
    sync = getattr(self, "_sync_shop_inventory_window", None)
    if callable(sync):
        sync()
        return
    if not hasattr(self, "_shop_inventory_window"):
        return
    self._shop_inventory_window.set_pet_state(self._save_game.pet_state)
    self._shop_inventory_window.set_inventory(self._save_game.inventory)


def on_startup_complete(self) -> None:
    resume_loaded_activity_animation(self)
    request_visual_state_update(self)
    self._sync_status_panel_info()


def on_playback_idle(self) -> None:
    self._care_playback.on_playback_idle()
    self._resume_activity_animation_if_needed()
    self._visual_state_bridge.apply_pending_if_possible()
    self._sync_status_panel_info()
    self._sync_activity_panel()
    self._refresh_dev_debug()


def on_care_playback_finished(self) -> None:
    self._visual_state_bridge.apply_pending_if_possible()
    self._sync_status_panel_info()
    self._sync_activity_panel()
    self._refresh_dev_debug()


def resume_loaded_activity_animation(self) -> None:
    if self._activity_playback.is_active():
        return
    activity = self._activity_system.current_activity()
    if activity is None:
        return
    playback = self._activity_playback.start_activity_animation(activity)
    if playback.message:
        show_activity_notice(self, playback.message)


def request_visual_state_update(self) -> None:
    self._visual_state_bridge.request_update()
    self._sync_status_panel_info()
    self._refresh_dev_debug()


def handle_playback_idle(self) -> None:
    self.on_playback_idle()


def handle_director_pet_state_changed(self, _pet_state: str) -> None:
    self._sync_status_panel_info()
    self._refresh_dev_debug()
