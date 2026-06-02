"""独立商店/背包窗口。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PyQt6.QtCore import QEvent, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPixmap
from PyQt6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from core.raising.items import (
    PRIMARY_EFFECT_FIELD_BY_CATEGORY,
    ItemDefinition,
    inventory_count,
    item_has_actual_improvement,
    normalize_inventory,
    preview_item_effects,
    resolve_item_icon_path,
)
from core.raising.pet_state import PetState
from core.performance import measure_ui
from ui.shared.window_geometry import RememberedWindowGeometry

ICON_BOX_SIZE = 48
ICON_PIXMAP_SIZE = 40
ROW_BATCH_THRESHOLD = 64
ROW_BATCH_SIZE = 24
CATEGORY_FILTER_OPTIONS = (
    ("", "全部"),
    ("food", "食物"),
    ("drink", "饮料"),
    ("medicine", "药品"),
    ("cleaning", "清洁用品"),
    ("gift", "礼物"),
)
SHOP_SORT_OPTIONS = (
    ("default", "默认排序"),
    ("name", "按名称排序"),
    ("price", "按价格排序"),
)


@dataclass(slots=True)
class _ShopRow:
    widget: QWidget
    count_label: QLabel
    purchase_button: QPushButton


@dataclass(slots=True)
class _InventoryRow:
    widget: QWidget
    count_label: QLabel
    use_button: QPushButton


@dataclass(slots=True)
class _IconCacheStats:
    path_hits: int = 0
    path_misses: int = 0
    pixmap_hits: int = 0
    pixmap_misses: int = 0


class _ItemIconCache:
    def __init__(self) -> None:
        self._resolved_paths: dict[str, Path | None] = {}
        self._pixmaps: dict[tuple[str, int], QPixmap] = {}
        self._stats = _IconCacheStats()

    def pixmap_for_item(self, item: ItemDefinition, size: int) -> QPixmap | None:
        icon_path = self._icon_path(item)
        if icon_path is None:
            return None
        key = (str(icon_path), max(1, int(size)))
        cached = self._pixmaps.get(key)
        if cached is not None:
            self._stats.pixmap_hits += 1
            return cached

        self._stats.pixmap_misses += 1
        with measure_ui("shop.icon.load_scaled", detail=Path(key[0]).name):
            pixmap = QPixmap(key[0])
            if pixmap.isNull():
                return None
            scaled = pixmap.scaled(
                key[1],
                key[1],
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        self._pixmaps[key] = scaled
        return scaled

    def clear(self) -> None:
        self._resolved_paths.clear()
        self._pixmaps.clear()
        self._stats = _IconCacheStats()

    def stats(self) -> dict[str, int]:
        return {
            "path_hits": self._stats.path_hits,
            "path_misses": self._stats.path_misses,
            "pixmap_hits": self._stats.pixmap_hits,
            "pixmap_misses": self._stats.pixmap_misses,
            "cached_pixmaps": len(self._pixmaps),
            "cached_paths": len(self._resolved_paths),
        }

    def _icon_path(self, item: ItemDefinition) -> Path | None:
        key = str(item.icon).strip()
        if key in self._resolved_paths:
            self._stats.path_hits += 1
            return self._resolved_paths[key]
        self._stats.path_misses += 1
        path = resolve_item_icon_path(item)
        self._resolved_paths[key] = path
        return path


_ITEM_ICON_CACHE = _ItemIconCache()


class ShopInventoryWindow(QWidget):
    purchase_requested = pyqtSignal(str)
    use_requested = pyqtSignal(str)

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        geometry_settings_path: Path | None = None,
    ) -> None:
        super().__init__(parent, Qt.WindowType.Window)
        self.setWindowTitle("商店 / 背包")
        self.setMinimumSize(680, 460)
        self._remembered_geometry = RememberedWindowGeometry(
            self,
            "shop_inventory",
            settings_path=geometry_settings_path,
        )
        self._remembered_geometry.restore()

        self._item_catalog: tuple[ItemDefinition, ...] = ()
        self._known_items_by_id: dict[str, ItemDefinition] = {}
        self._inventory: dict[str, int] = {}
        self._state = PetState()
        self._applying_style = False
        self._shop_dirty = True
        self._inventory_dirty = True
        self._shop_rebuild_pending = False
        self._inventory_rebuild_pending = False
        self._shop_rebuild_reason = "initial"
        self._inventory_rebuild_reason = "initial"
        self._shop_batch_generation = 0
        self._shop_batch_items: tuple[ItemDefinition, ...] = ()
        self._shop_batch_index = 0
        self._inventory_batch_generation = 0
        self._inventory_batch_entries: tuple[tuple[str, object, int], ...] = ()
        self._inventory_batch_index = 0
        self._shop_rows: dict[str, _ShopRow] = {}
        self._inventory_rows: dict[str, _InventoryRow] = {}
        self._unknown_inventory_rows: dict[str, _InventoryRow] = {}
        self._header_rows: dict[tuple[str, ...], QWidget] = {}
        self._placeholder_labels: dict[str, QLabel] = {}
        self._shop_category_combo = self._category_combo("shopCategoryCombo")
        self._shop_sort_combo = self._shop_sort_combo_widget()
        self._inventory_category_combo = self._category_combo("inventoryCategoryCombo")

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        root.addLayout(self._build_summary_row())

        self._notice_label = QLabel("")
        self._notice_label.setObjectName("noticeLabel")
        self._notice_label.setWordWrap(True)
        self._notice_label.hide()
        root.addWidget(self._notice_label)

        self._tabs = QTabWidget()
        self._tabs.setObjectName("shopInventoryTabs")
        self._shop_list = QVBoxLayout()
        self._inventory_list = QVBoxLayout()
        self._tabs.addTab(
            self._list_page(self._build_shop_controls(), self._shop_list),
            "商店",
        )
        self._tabs.addTab(
            self._list_page(self._build_inventory_controls(), self._inventory_list),
            "背包",
        )
        root.addWidget(self._tabs, 1)

        self._shop_category_combo.currentIndexChanged.connect(
            lambda _index: self._on_shop_filter_changed("category")
        )
        self._shop_sort_combo.currentIndexChanged.connect(
            lambda _index: self._on_shop_filter_changed("sort")
        )
        self._inventory_category_combo.currentIndexChanged.connect(
            lambda _index: self._on_inventory_filter_changed()
        )
        self._tabs.currentChanged.connect(lambda _index: self._flush_current_page("tab"))

        self._apply_window_style()

    def show_page(self, page: str) -> None:
        page = "inventory" if page == "inventory" else "shop"
        with measure_ui("shop_inventory.open", detail=page):
            if not self.isVisible():
                self._remembered_geometry.restore()
            self._tabs.setCurrentIndex(1 if page == "inventory" else 0)
            self._flush_page(page, "open")
            self.show()
            self.raise_()
            self.activateWindow()
            self._remembered_geometry.enable_soon()

    def set_item_catalog(self, items: tuple[ItemDefinition, ...]) -> None:
        self._item_catalog = tuple(items)
        self._known_items_by_id = {item.id: item for item in self._item_catalog}
        self._clear_row_caches()
        self._mark_shop_dirty("catalog")
        self._mark_inventory_dirty("catalog")

    def set_pet_state(self, state: PetState) -> None:
        with measure_ui("shop_inventory.set_pet_state"):
            self._state = state
            self._money_label.setText(str(max(0, int(state.money))))
            self._refresh_inventory_rows()

    def set_inventory(self, inventory: dict[str, int]) -> None:
        with measure_ui("shop_inventory.set_inventory"):
            old_inventory = self._inventory
            new_inventory = normalize_inventory(inventory)
            changed_ids = _changed_inventory_ids(old_inventory, new_inventory)
            inventory_layout_changed = _inventory_visible_ids(old_inventory) != _inventory_visible_ids(
                new_inventory
            )
            self._inventory = new_inventory
            self._items_label.setText(str(inventory_count(self._inventory)))
            self._refresh_shop_rows(changed_ids)
            if inventory_layout_changed:
                self._mark_inventory_dirty("inventory")
            else:
                self._refresh_inventory_rows(changed_ids)

    def set_notice(self, message: str) -> None:
        message = str(message).strip()
        self._notice_label.setText(message)
        self._notice_label.setVisible(bool(message))

    def mark_dirty(self) -> None:
        self._mark_shop_dirty("external")
        self._mark_inventory_dirty("external")

    def _on_shop_filter_changed(self, reason: str) -> None:
        with measure_ui(f"shop.switch_{reason}"):
            self._mark_shop_dirty(reason)

    def _on_inventory_filter_changed(self) -> None:
        with measure_ui("inventory.switch_category"):
            self._mark_inventory_dirty("category")

    def _flush_current_page(self, reason: str) -> None:
        self._flush_page("inventory" if self._tabs.currentIndex() == 1 else "shop", reason)

    def _flush_page(self, page: str, reason: str) -> None:
        if page == "inventory":
            self._perform_inventory_rebuild(reason)
        else:
            self._perform_shop_rebuild(reason)

    def _mark_shop_dirty(self, reason: str) -> None:
        self._shop_dirty = True
        self._shop_rebuild_reason = reason
        if self.isVisible() and self._tabs.currentIndex() == 0:
            self._schedule_shop_rebuild(reason)

    def _mark_inventory_dirty(self, reason: str) -> None:
        self._inventory_dirty = True
        self._inventory_rebuild_reason = reason
        if self.isVisible() and self._tabs.currentIndex() == 1:
            self._schedule_inventory_rebuild(reason)

    def _schedule_shop_rebuild(self, reason: str) -> None:
        self._shop_rebuild_reason = reason
        if self._shop_rebuild_pending:
            return
        self._shop_rebuild_pending = True
        QTimer.singleShot(0, lambda: self._perform_shop_rebuild(self._shop_rebuild_reason))

    def _schedule_inventory_rebuild(self, reason: str) -> None:
        self._inventory_rebuild_reason = reason
        if self._inventory_rebuild_pending:
            return
        self._inventory_rebuild_pending = True
        QTimer.singleShot(
            0,
            lambda: self._perform_inventory_rebuild(self._inventory_rebuild_reason),
        )

    def _perform_shop_rebuild(self, reason: str) -> None:
        self._shop_rebuild_pending = False
        if not self._shop_dirty:
            return
        self._rebuild_shop_page(reason=reason)

    def _perform_inventory_rebuild(self, reason: str) -> None:
        self._inventory_rebuild_pending = False
        if not self._inventory_dirty:
            return
        self._rebuild_inventory_page(reason=reason)

    def _build_summary_row(self) -> QHBoxLayout:
        money_title = QLabel("金币")
        money_title.setObjectName("summaryTitle")
        self._money_label = QLabel("0")
        self._money_label.setObjectName("summaryValue")

        items_title = QLabel("背包")
        items_title.setObjectName("summaryTitle")
        self._items_label = QLabel("0")
        self._items_label.setObjectName("summaryValue")

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        row.addWidget(money_title)
        row.addWidget(self._money_label)
        row.addSpacing(14)
        row.addWidget(items_title)
        row.addWidget(self._items_label)
        row.addStretch(1)
        return row

    def _scroll_page(self, list_layout: QVBoxLayout) -> QScrollArea:
        list_layout.setContentsMargins(0, 0, 0, 0)
        list_layout.setSpacing(0)
        list_layout.addStretch(1)

        content = QWidget()
        content.setObjectName("listContent")
        content.setLayout(list_layout)

        scroll = QScrollArea()
        scroll.setObjectName("itemScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(content)
        return scroll

    def _list_page(self, controls: QHBoxLayout, list_layout: QVBoxLayout) -> QWidget:
        page = QWidget()
        page.setObjectName("listPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addLayout(controls)
        layout.addWidget(self._scroll_page(list_layout), 1)
        return page

    def _build_shop_controls(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        row.addWidget(_control_label("分类"))
        row.addWidget(self._shop_category_combo)
        row.addSpacing(8)
        row.addWidget(_control_label("排序"))
        row.addWidget(self._shop_sort_combo)
        row.addStretch(1)
        return row

    def _build_inventory_controls(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        row.addWidget(_control_label("分类"))
        row.addWidget(self._inventory_category_combo)
        row.addStretch(1)
        return row

    def _category_combo(self, object_name: str) -> QComboBox:
        combo = QComboBox()
        combo.setObjectName(object_name)
        combo.setMinimumWidth(112)
        for category, label in CATEGORY_FILTER_OPTIONS:
            combo.addItem(label, category)
        return combo

    def _shop_sort_combo_widget(self) -> QComboBox:
        combo = QComboBox()
        combo.setObjectName("shopSortCombo")
        combo.setMinimumWidth(128)
        for mode, label in SHOP_SORT_OPTIONS:
            combo.addItem(label, mode)
        return combo

    def _rebuild_shop_page(self, *, reason: str = "refresh") -> None:
        with measure_ui("shop.refresh_list", detail=reason):
            self._shop_dirty = False
            self._cancel_shop_batch()
            self._detach_list(self._shop_list)
            if not self._item_catalog:
                self._shop_list.addWidget(self._placeholder("shop_empty", "暂无商品"))
                self._shop_list.addStretch(1)
                return

            category = _combo_data(self._shop_category_combo)
            sort_mode = _combo_data(self._shop_sort_combo, default="default")
            if category:
                visible_items = _filtered_sorted_catalog_items(
                    self._item_catalog,
                    category=category,
                    sort_mode=sort_mode,
                )
            else:
                with measure_ui("shop.display_all_items", detail=sort_mode):
                    visible_items = _filtered_sorted_catalog_items(
                        self._item_catalog,
                        category=category,
                        sort_mode=sort_mode,
                    )
            if not visible_items:
                self._shop_list.addWidget(
                    self._placeholder("shop_category_empty", "当前分类暂无商品")
                )
                self._shop_list.addStretch(1)
                return

            self.setUpdatesEnabled(False)
            try:
                self._shop_list.addWidget(
                    self._header_row(("", "分类", "名称 / 描述", "价格", "效果", "持有", ""))
                )
                if len(visible_items) > ROW_BATCH_THRESHOLD:
                    self._start_shop_batch(visible_items)
                else:
                    for item in visible_items:
                        self._shop_list.addWidget(self._shop_row(item))
                    self._shop_list.addStretch(1)
            finally:
                self.setUpdatesEnabled(True)

    def _rebuild_inventory_page(self, *, reason: str = "refresh") -> None:
        with measure_ui("inventory.refresh_list", detail=reason):
            self._inventory_dirty = False
            self._cancel_inventory_batch()
            self._detach_list(self._inventory_list)
            if not self._inventory:
                self._inventory_list.addWidget(
                    self._placeholder("inventory_empty", "背包是空的，可以先在商店买一点。")
                )
                self._inventory_list.addStretch(1)
                return

            category = _combo_data(self._inventory_category_combo)
            self.setUpdatesEnabled(False)
            try:
                self._inventory_list.addWidget(
                    self._header_row(("", "分类", "名称", "数量", "效果", "", ""))
                )
                entries: list[tuple[str, object, int]] = []
                ordered_items = (
                    item
                    for item in _filtered_sorted_catalog_items(
                        self._item_catalog,
                        category=category,
                        sort_mode="default",
                    )
                    if self._inventory.get(item.id, 0) > 0
                )
                shown = 0
                for item in ordered_items:
                    count = max(0, int(self._inventory.get(item.id, 0)))
                    entries.append(("known", item, count))
                    shown += 1
                if not category:
                    unknown_ids = sorted(
                        item_id
                        for item_id in self._inventory
                        if item_id not in self._known_items_by_id
                    )
                    for item_id in unknown_ids:
                        count = max(0, int(self._inventory.get(item_id, 0)))
                        if count <= 0:
                            continue
                        entries.append(("unknown", item_id, count))
                        shown += 1
                if shown <= 0:
                    self._inventory_list.addWidget(
                        self._placeholder("inventory_category_empty", "当前分类没有背包物品")
                    )
                elif len(entries) > ROW_BATCH_THRESHOLD:
                    self._start_inventory_batch(tuple(entries))
                else:
                    for entry in entries:
                        self._inventory_list.addWidget(self._inventory_entry_row(entry))
                    self._inventory_list.addStretch(1)
            finally:
                self.setUpdatesEnabled(True)

    def has_pending_row_batches(self) -> bool:
        return bool(self._shop_batch_items or self._inventory_batch_entries)

    def _cancel_shop_batch(self) -> None:
        self._shop_batch_generation += 1
        self._shop_batch_items = ()
        self._shop_batch_index = 0

    def _start_shop_batch(self, items: tuple[ItemDefinition, ...]) -> None:
        self._shop_batch_items = items
        self._shop_batch_index = 0
        generation = self._shop_batch_generation
        self._append_shop_batch(generation)

    def _append_shop_batch(self, generation: int) -> None:
        if generation != self._shop_batch_generation or not self._shop_batch_items:
            return
        with measure_ui("shop.append_row_batch"):
            start = self._shop_batch_index
            end = min(len(self._shop_batch_items), start + ROW_BATCH_SIZE)
            self.setUpdatesEnabled(False)
            try:
                for item in self._shop_batch_items[start:end]:
                    self._shop_list.addWidget(self._shop_row(item))
                if end >= len(self._shop_batch_items):
                    self._shop_list.addStretch(1)
                    self._shop_batch_items = ()
                    self._shop_batch_index = 0
                    return
                self._shop_batch_index = end
            finally:
                self.setUpdatesEnabled(True)
        QTimer.singleShot(0, lambda: self._append_shop_batch(generation))

    def _cancel_inventory_batch(self) -> None:
        self._inventory_batch_generation += 1
        self._inventory_batch_entries = ()
        self._inventory_batch_index = 0

    def _start_inventory_batch(self, entries: tuple[tuple[str, object, int], ...]) -> None:
        self._inventory_batch_entries = entries
        self._inventory_batch_index = 0
        generation = self._inventory_batch_generation
        self._append_inventory_batch(generation)

    def _append_inventory_batch(self, generation: int) -> None:
        if generation != self._inventory_batch_generation or not self._inventory_batch_entries:
            return
        with measure_ui("inventory.append_row_batch"):
            start = self._inventory_batch_index
            end = min(len(self._inventory_batch_entries), start + ROW_BATCH_SIZE)
            self.setUpdatesEnabled(False)
            try:
                for entry in self._inventory_batch_entries[start:end]:
                    self._inventory_list.addWidget(self._inventory_entry_row(entry))
                if end >= len(self._inventory_batch_entries):
                    self._inventory_list.addStretch(1)
                    self._inventory_batch_entries = ()
                    self._inventory_batch_index = 0
                    return
                self._inventory_batch_index = end
            finally:
                self.setUpdatesEnabled(True)
        QTimer.singleShot(0, lambda: self._append_inventory_batch(generation))

    def _header_row(self, titles: tuple[str, ...]) -> QWidget:
        cached = self._header_rows.get(titles)
        if cached is not None:
            return cached
        row = QWidget()
        row.setObjectName("headerRow")
        grid = self._row_grid(row)
        for column, title in enumerate(titles):
            label = QLabel(title)
            label.setObjectName("headerLabel")
            grid.addWidget(label, 0, column)
        self._header_rows[titles] = row
        return row

    def _shop_row(self, item: ItemDefinition) -> QWidget:
        cached = self._shop_rows.get(item.id)
        if cached is not None:
            self._update_shop_row(cached, item)
            return cached.widget

        row = QWidget()
        row.setObjectName("itemRow")
        tooltip = _item_tooltip(item)
        row.setToolTip(tooltip)
        grid = self._row_grid(row)

        grid.addWidget(_item_icon_label(item, tooltip), 0, 0)
        grid.addWidget(_text_label(_category_label(item.category), tooltip), 0, 1)
        grid.addWidget(_name_description_label(item.name, item.description, tooltip), 0, 2)
        grid.addWidget(_text_label(f"{item.price} 金币", tooltip), 0, 3)
        grid.addWidget(_text_label(_item_effect_summary(item), tooltip), 0, 4)
        count_label = _text_label("", tooltip)
        grid.addWidget(count_label, 0, 5)

        button = QPushButton("购买")
        button.setObjectName(f"purchaseButton_{item.id}")
        button.setToolTip(tooltip)
        button.clicked.connect(
            lambda checked=False, item_id=item.id: self.purchase_requested.emit(item_id)
        )
        grid.addWidget(button, 0, 6)
        cached = _ShopRow(row, count_label, button)
        self._shop_rows[item.id] = cached
        self._update_shop_row(cached, item)
        return row

    def _inventory_entry_row(self, entry: tuple[str, object, int]) -> QWidget:
        kind, payload, count = entry
        if kind == "known" and isinstance(payload, ItemDefinition):
            return self._inventory_row(payload, count)
        return self._unknown_inventory_row(str(payload), count)

    def _inventory_row(self, item: ItemDefinition, count: int) -> QWidget:
        cached = self._inventory_rows.get(item.id)
        if cached is not None:
            self._update_inventory_row(cached, item, count)
            return cached.widget

        row = QWidget()
        row.setObjectName("itemRow")
        tooltip = _item_tooltip(item)
        row.setToolTip(tooltip)
        grid = self._row_grid(row)

        grid.addWidget(_item_icon_label(item, tooltip), 0, 0)
        grid.addWidget(_text_label(_category_label(item.category), tooltip), 0, 1)
        grid.addWidget(_text_label(item.name, tooltip), 0, 2)
        count_label = _text_label("", tooltip)
        grid.addWidget(count_label, 0, 3)
        grid.addWidget(_text_label(_item_effect_summary(item), tooltip), 0, 4)
        grid.addWidget(QWidget(), 0, 5)

        button = QPushButton("使用")
        button.setObjectName(f"useButton_{item.id}")
        button.clicked.connect(
            lambda checked=False, item_id=item.id: self.use_requested.emit(item_id)
        )
        grid.addWidget(button, 0, 6)
        cached = _InventoryRow(row, count_label, button)
        self._inventory_rows[item.id] = cached
        self._update_inventory_row(cached, item, count)
        return row

    def _unknown_inventory_row(self, item_id: str, count: int) -> QWidget:
        cached = self._unknown_inventory_rows.get(item_id)
        if cached is not None:
            cached.count_label.setText(f"x{count}")
            return cached.widget

        row = QWidget()
        row.setObjectName("itemRow")
        tooltip = "物品配置中找不到这个 id。"
        grid = self._row_grid(row)
        grid.addWidget(_empty_icon_label(tooltip), 0, 0)
        grid.addWidget(_text_label("未知", tooltip), 0, 1)
        grid.addWidget(_text_label(item_id, tooltip), 0, 2)
        count_label = _text_label("", tooltip)
        grid.addWidget(count_label, 0, 3)
        grid.addWidget(_text_label("配置缺失", tooltip), 0, 4)
        grid.addWidget(QWidget(), 0, 5)
        button = QPushButton("使用")
        button.setObjectName(f"useButton_{item_id}")
        button.setEnabled(False)
        button.setToolTip(tooltip)
        grid.addWidget(button, 0, 6)
        cached = _InventoryRow(row, count_label, button)
        self._unknown_inventory_rows[item_id] = cached
        cached.count_label.setText(f"x{count}")
        return row

    def _update_shop_row(self, row: _ShopRow, item: ItemDefinition) -> None:
        row.count_label.setText(f"x{max(0, int(self._inventory.get(item.id, 0)))}")

    def _update_inventory_row(
        self,
        row: _InventoryRow,
        item: ItemDefinition,
        count: int,
    ) -> None:
        tooltip = _item_tooltip(item)
        row.count_label.setText(f"x{max(0, int(count))}")
        reason = self._unavailable_use_reason(item, count)
        row.use_button.setEnabled(not reason)
        row.use_button.setToolTip(reason or tooltip)

    def _refresh_shop_rows(self, item_ids: set[str] | None = None) -> None:
        targets = item_ids if item_ids is not None else set(self._shop_rows)
        for item_id in targets:
            row = self._shop_rows.get(item_id)
            item = self._known_items_by_id.get(item_id)
            if row is not None and item is not None:
                self._update_shop_row(row, item)

    def _refresh_inventory_rows(self, item_ids: set[str] | None = None) -> None:
        targets = item_ids if item_ids is not None else set(self._inventory_rows)
        for item_id in targets:
            row = self._inventory_rows.get(item_id)
            item = self._known_items_by_id.get(item_id)
            if row is not None and item is not None:
                self._update_inventory_row(
                    row,
                    item,
                    max(0, int(self._inventory.get(item_id, 0))),
                )
            unknown_row = self._unknown_inventory_rows.get(item_id)
            if unknown_row is not None:
                unknown_row.count_label.setText(
                    f"x{max(0, int(self._inventory.get(item_id, 0)))}"
                )

    def _placeholder(self, key: str, text: str) -> QLabel:
        label = self._placeholder_labels.get(key)
        if label is None:
            label = _placeholder_label(text)
            self._placeholder_labels[key] = label
        else:
            label.setText(text)
        return label

    def _row_grid(self, row: QWidget) -> QGridLayout:
        grid = QGridLayout(row)
        grid.setContentsMargins(8, 7, 8, 7)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(0)
        grid.setColumnMinimumWidth(0, ICON_BOX_SIZE)
        grid.setColumnMinimumWidth(1, 58)
        grid.setColumnMinimumWidth(3, 68)
        grid.setColumnMinimumWidth(5, 48)
        grid.setColumnMinimumWidth(6, 66)
        grid.setColumnStretch(2, 3)
        grid.setColumnStretch(4, 2)
        return grid

    def _unavailable_use_reason(self, item: ItemDefinition, count: int) -> str:
        if count <= 0:
            return f"背包里没有 {item.name}。"
        if item_has_actual_improvement(self._state, item):
            return ""

        primary_field = PRIMARY_EFFECT_FIELD_BY_CATEGORY.get(item.category)
        if primary_field in item.effects:
            deltas = preview_item_effects(self._state, item.effects)
            if deltas.get(primary_field, 0) <= 0:
                return f"{_field_label(primary_field)}已满，暂时用不上。"
        return f"{item.name} 现在用不上，状态已经足够好了。"

    def _detach_list(self, layout: QVBoxLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)

    def _clear_row_caches(self) -> None:
        self._cancel_shop_batch()
        self._cancel_inventory_batch()
        self._detach_list(self._shop_list)
        self._detach_list(self._inventory_list)
        for cache in (self._shop_rows, self._inventory_rows, self._unknown_inventory_rows):
            for row in cache.values():
                row.widget.setParent(None)
                row.widget.deleteLater()
            cache.clear()

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if (
            event.type() == QEvent.Type.PaletteChange
            and not getattr(self, "_applying_style", False)
        ):
            self._apply_window_style()

    def moveEvent(self, event) -> None:
        super().moveEvent(event)
        self._remembered_geometry.schedule_save()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._remembered_geometry.schedule_save()

    def closeEvent(self, event) -> None:
        self._remembered_geometry.save_now()
        self._remembered_geometry.disable()
        super().closeEvent(event)

    def _apply_window_style(self) -> None:
        if self._applying_style:
            return
        self._applying_style = True
        palette = self.palette()
        window = palette.window().color()
        base = palette.base().color()
        text = palette.text().color()
        button = palette.button().color()
        highlight = palette.highlight().color()
        mid = palette.mid().color()
        disabled = _blend(text, window, 0.54)
        try:
            self.setStyleSheet(
                _WINDOW_STYLE_TEMPLATE.format(
                    window_bg=_hex(window),
                    base_bg=_rgba(base, 0.92),
                    row_bg=_rgba(base, 0.62),
                    row_alt_bg=_rgba(button, 0.34),
                    border=_rgba(mid, 0.36),
                    text=_hex(text),
                    text_soft=_rgba(text, 0.72),
                    text_disabled=_hex(disabled),
                    button_bg=_rgba(button, 0.88),
                    button_hover=_rgba(_blend(button, highlight, 0.12), 0.96),
                    button_pressed=_rgba(_blend(button, highlight, 0.22), 0.96),
                    icon_bg=_rgba(_blend(base, button, 0.18), 0.72),
                    accent=_hex(highlight),
                )
            )
        finally:
            self._applying_style = False


def _filtered_sorted_catalog_items(
    items: tuple[ItemDefinition, ...],
    *,
    category: str = "",
    sort_mode: str = "default",
) -> tuple[ItemDefinition, ...]:
    indexed_items = [
        (index, item)
        for index, item in enumerate(items)
        if not category or item.category == category
    ]
    if sort_mode == "name":
        indexed_items.sort(key=lambda pair: (pair[1].name, pair[0]))
    elif sort_mode == "price":
        indexed_items.sort(key=lambda pair: (pair[1].price, pair[0]))
    return tuple(item for _index, item in indexed_items)


def _changed_inventory_ids(
    old_inventory: dict[str, int],
    new_inventory: dict[str, int],
) -> set[str]:
    item_ids = set(old_inventory) | set(new_inventory)
    return {
        item_id
        for item_id in item_ids
        if max(0, int(old_inventory.get(item_id, 0)))
        != max(0, int(new_inventory.get(item_id, 0)))
    }


def _inventory_visible_ids(inventory: dict[str, int]) -> set[str]:
    return {
        item_id
        for item_id, count in inventory.items()
        if max(0, int(count)) > 0
    }


def clear_item_icon_cache() -> None:
    _ITEM_ICON_CACHE.clear()


def item_icon_cache_stats() -> dict[str, int]:
    return _ITEM_ICON_CACHE.stats()


def _combo_data(combo: QComboBox, *, default: str = "") -> str:
    value = combo.currentData()
    if value is None:
        return default
    text = str(value).strip()
    return text or default


def _category_label(category: str) -> str:
    labels = {
        "food": "食物",
        "drink": "饮料",
        "medicine": "药品",
        "cleaning": "清洁用品",
        "gift": "礼物",
    }
    return labels.get(category, category)


def _field_label(field: str) -> str:
    labels = {
        "satiety": "饱腹",
        "mood": "心情",
        "energy": "体力",
        "health": "健康",
        "cleanliness": "清洁",
        "affection": "亲密度",
    }
    return labels.get(field, field)


def _effect_text(effects: dict[str, int]) -> str:
    parts: list[str] = []
    for field, amount in effects.items():
        sign = "+" if amount > 0 else ""
        parts.append(f"{_field_label(field)} {sign}{amount}")
    return "、".join(parts)


def _item_effect_summary(item: ItemDefinition) -> str:
    return _effect_text(item.effects)


def _item_tooltip(item: ItemDefinition) -> str:
    effect = _effect_text(item.effects)
    if item.description:
        return f"{item.description}\n效果：{effect}"
    return f"效果：{effect}"


def _item_icon_label(item: ItemDefinition, tooltip: str = "") -> QLabel:
    label = _empty_icon_label(tooltip)
    pixmap = _ITEM_ICON_CACHE.pixmap_for_item(item, ICON_PIXMAP_SIZE)
    if pixmap is not None and not pixmap.isNull():
        label.setPixmap(pixmap)
    return label


def _empty_icon_label(tooltip: str = "") -> QLabel:
    label = QLabel()
    label.setObjectName("itemIconLabel")
    label.setFixedSize(ICON_BOX_SIZE, ICON_BOX_SIZE)
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    if tooltip:
        label.setToolTip(tooltip)
    return label


def _text_label(text: str, tooltip: str = "") -> QLabel:
    label = QLabel(text)
    label.setObjectName("rowLabel")
    label.setWordWrap(True)
    label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
    if tooltip:
        label.setToolTip(tooltip)
    return label


def _control_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("controlLabel")
    return label


def _name_description_label(name: str, description: str, tooltip: str) -> QLabel:
    text = name if not description else f"{name}\n{description}"
    label = _text_label(text, tooltip)
    label.setObjectName("nameDescriptionLabel")
    return label


def _placeholder_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("placeholderLabel")
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    return label


def _hex(color: QColor) -> str:
    return color.name()


def _rgba(color: QColor, alpha: float) -> str:
    alpha_i = max(0, min(255, round(alpha * 255)))
    return f"rgba({color.red()}, {color.green()}, {color.blue()}, {alpha_i})"


def _blend(a: QColor, b: QColor, ratio: float) -> QColor:
    ratio = max(0.0, min(1.0, ratio))
    return QColor(
        round(a.red() * (1.0 - ratio) + b.red() * ratio),
        round(a.green() * (1.0 - ratio) + b.green() * ratio),
        round(a.blue() * (1.0 - ratio) + b.blue() * ratio),
    )


_WINDOW_STYLE_TEMPLATE = """
QWidget {{
    background: {window_bg};
    color: {text};
}}
QLabel {{
    color: {text_soft};
}}
QLabel#summaryTitle,
QLabel#headerLabel {{
    color: {text_soft};
    font-weight: 600;
}}
QLabel#summaryValue,
QLabel#noticeLabel {{
    color: {text};
    font-weight: 700;
}}
QLabel#placeholderLabel {{
    padding: 24px 0;
    color: {text_soft};
}}
QLabel#nameDescriptionLabel {{
    color: {text};
}}
QLabel#itemIconLabel {{
    background: {icon_bg};
    border: 1px solid {border};
    border-radius: 6px;
}}
QTabWidget::pane {{
    border: 1px solid {border};
    border-radius: 8px;
    background: {base_bg};
}}
QTabBar::tab {{
    padding: 7px 16px;
    color: {text_soft};
}}
QTabBar::tab:selected {{
    color: {text};
    border-bottom: 2px solid {accent};
}}
QScrollArea#itemScroll,
QWidget#listContent,
QWidget#listPage {{
    background: transparent;
}}
QWidget#headerRow {{
    background: transparent;
    border-bottom: 1px solid {border};
}}
QWidget#itemRow {{
    background: {row_bg};
    border-bottom: 1px solid {border};
}}
QWidget#itemRow:hover {{
    background: {row_alt_bg};
}}
QPushButton {{
    background: {button_bg};
    border: 1px solid {border};
    border-radius: 8px;
    padding: 6px 10px;
    color: {text};
}}
QPushButton:hover {{
    background: {button_hover};
}}
QPushButton:pressed {{
    background: {button_pressed};
}}
QPushButton:disabled {{
    color: {text_disabled};
}}
QComboBox {{
    background: {button_bg};
    border: 1px solid {border};
    border-radius: 8px;
    padding: 5px 8px;
    color: {text};
}}
QComboBox:hover {{
    background: {button_hover};
}}
"""
