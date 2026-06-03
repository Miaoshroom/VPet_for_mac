# 存档文件说明

`saves/savegame.json` 是桌宠养成系统的存档文件，记录宠物的状态、背包物品和系统设置。

正常玩不建议改存档喵。。

## 顶层字段

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `version` | 整数 | 存档格式版本号，当前为 `3` |
| `pet_state` | 对象 | 宠物当前各项状态值 |
| `inventory` | 对象 | 背包里的物品及数量 |
| `activity_progress` | 对象或 null | 当前正在进行的活动进度，无活动时为 `null` |
| `status_decay_enabled` | 布尔 | 是否开启状态自然衰减（随时间缓慢下降） |
| `auto_refill_enabled` | 布尔 | 状态低于阈值时是否自动使用背包物品补充 |
| `auto_purchase_enabled` | 布尔 | 背包无对应物品时是否自动从商店购买 |
| `last_saved_at` | 字符串 | 最后一次保存时间 |

## pet_state 宠物状态

| 字段 | 类型 | 范围 | 说明 |
| --- | --- | --- | --- |
| `money` | 整数 | 0+ | 金币，通过活动和打工获取 |
| `satiety` | 整数 | 0–100 | 饱腹度，随时间下降，吃食物恢复 |
| `mood` | 整数 | 0–100 | 心情，影响宠物表现状态（happy → normal → poor_condition → ill） |
| `energy` | 整数 | 0–100 | 体力，活动消耗的主要属性 |
| `health` | 整数 | 0–100 | 健康，生病时需要药品恢复 |
| `cleanliness` | 整数 | 0–100 | 清洁度，随时间下降，使用清洁物品恢复 |
| `exp` | 整数 | 0+ | 经验值，累计到一定值触发升级 |
| `level` | 整数 | 1+ | 当前等级 |
| `affection` | 整数 | 0+ | 亲密度，通过送礼物和互动提升 |
| `current_activity` | 字符串 | — | 当前活动名称，空闲时显示"待机" |

## inventory 背包

以物品 id 为键，数量为值。物品 id 对应 `config/item_catalog.json` 里定义的物品。

```json
{
  "rice_ball": 5,
  "sparkling_water": 9,
  "cleaning_wipes": 2
}
```

## activity_progress 活动进度

进行活动时记录进度信息，无活动时为 `null`。

## 注意事项

1. 手改存档后需要重启桌宠才会生效。
2. 状态值超出 0–100 范围可能导致意外行为。
3. `inventory` 里的物品 id 如果不在 `item_catalog.json` 里，会被视为无效物品。
