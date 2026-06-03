# 素材与配置修改指南

主要内容：文档入口页。换桌宠图片、加动作、调自动行为、开关插件等都先看这个。

## 可以改什么

- 替换已有动画的图片帧
- 给已有动作补充不同状态的素材
- 新增一个动作，并让它出现在菜单或自动待机里
- 调整启动、退出、随机插入动画
- 调整鼠标按压、拖动不同区域时触发的动作
- 调整桌宠自动移动的动作、速度和边界
- 配置活动（工作、学习、运动、休息等），调整需求、消耗和奖励
- 配置商店物品目录，修改价格、效果等
- 开关插件，或修改插件自己的配置

## 文档入口

| 想做的事 | 看哪里 |
| --- | --- |
| 替换图片、整理动画目录、新增动作素材 | [ASSETS.md](ASSETS.md) |
| 开关插件、修改插件参数、了解插件命名 | [PLUGINS.md](PLUGINS.md) |
| 桌宠存档文件 | [SAVES.md](PLUGINS.md) |
| 使用编辑器调整一些难以手动编辑的配置文件 | [EDITOR.md](EDITOR.md) |
| 调默认动作、自动待机、启动退出动画 | 本文的 `action_settings.json` 说明 |
| 调活动配置、动画候选 | 本文的 `activity_settings.json` 说明 |
| 调商店物品、价格、效果 | 本文的 `item_catalog.json` 说明 |
| 调鼠标互动区域 | 本文的 `interaction_map.json` 说明 |
| 调自动移动 | 本文的 `move_settings.json` 说明 |

其中 `modes.json` , `action_settings.json` , `plugin_loader.json` ， `interaction_map.json` 可在桌宠编辑器中编辑
## 注意事项x

1. JSON 文件不能有注释，逗号也要严格。
2. 动作 id 必须和 `assets/animations/<动作id>` 的目录名一致。
3. `any` 是素材兜底目录，不是桌宠的第五种状态。

桌宠真正的表现状态只有：

```text
happy
normal
poor_condition
ill
```

如果某个动作没有当前状态的素材，桌宠才会尝试找同动作下的 `any`。

## 常用配置文件

| 文件 | 做什么的 |
| --- | --- |
| `config/modes.json` | 注册动作：动作 id、菜单显示名、动作类型 |
| `config/action_settings.json` | 默认动作、提起动作、自动待机、启动退出动画、随机插入动画 |
| `config/interaction_map.json` | 鼠标按压、点击、拖动不同区域时触发什么 |
| `config/move_settings.json` | 自动移动开关、移动间隔、移动速度、屏幕边界 |
| `config/window_settings.json` | 开发模式开关，记录桌宠窗口大小、位置、UI 窗口位置 |
| `config/activity_settings.json` | 活动列表：工作、学习、运动、休息等，含需求、消耗和奖励 |
| `config/item_catalog.json` | 商店物品目录：食物、饮料、药品、清洁、礼物 |
| `config/app_settings.json` | 应用全局设置，目前只有存档位置 |
| `config/plugin_loader.json` | 启用哪些插件 |
| `config/plugin_config/*.json` | 插件自己的配置 |

## modes.json：动作注册表

每个动作都要先在 `config/modes.json` 里注册。

```json
{
  "id": "touch_head",
  "title": "摸头",
  "type": "phased"
}
```

| 字段 | 说明 |
| --- | --- |
| `id` | 动作 id，必须对应 `assets/animations/<动作id>` |
| `title` | 菜单里显示的中文名 |
| `type` | 动作类型，只能是 `loop`、`phased`、`single` |

动作类型怎么选：

| 类型 | 需要的素材阶段 | 适合什么 |
| --- | --- | --- |
| `loop` | `loop` | 一直循环播放的待机动作 |
| `phased` | `start`、`loop`、`end` | 有开始、持续、结束的动作，比如摸头、睡觉、跳舞 |
| `single` | `single` | 播一次就结束的动作，比如启动、退出、升级 |

## action_settings.json：默认动作

`config/action_settings.json` 控制桌宠自己会播的动作

| 字段 | 说明 |
| --- | --- |
| `default_mode` | 启动后进入的默认循环动作 |
| `press_mode` | 默认按住桌宠时触发的动作 |
| `auto_idle_modes` | 空闲时会随机切换的动作列表 |
| `idle_autoswitch_interval_min_ms` | 自动切换待机动作的最短间隔，单位毫秒 |
| `idle_autoswitch_interval_max_ms` | 自动切换待机动作的最长间隔，单位毫秒 |
| `startup` | 启动时随机选择的 `single` 动作列表 |
| `shutdown` | 退出时随机选择的 `single` 动作列表 |
| `single_insert_modes` | 空闲时随机插入的 `single` 动作列表 |
| `single_insert_interval_min_ms` | 随机插入单次动画的最短间隔 |
| `single_insert_interval_max_ms` | 随机插入单次动画的最长间隔 |

注意事项：这里引用的动作必须已经写在 `modes.json` 里。`auto_idle_modes` 只能放 `loop` 或 `phased`，`startup`、`shutdown`、`single_insert_modes` 只能放 `single`。

## interaction_map.json：鼠标互动区域配置

`config/interaction_map.json` 把桌宠显示区域切成一个网格，再指定某些格子被按压、点击、拖动时做什么。

当前配置使用：

```json
{
  "grid": {
    "rows": 7,
    "cols": 7
  }
}
```

意思是把桌宠画面切成 7 行、7 列。行列都从 0 开始数。

一个区域例子：

```json
{
  "name": "touch_head_handle",
  "row_start": 0,
  "row_end": 1,
  "col_start": 2,
  "col_end": 4,
  "press": {
    "type": "press_mode",
    "mode": "touch_head"
  }
}
```

这表示：按住第 0 到 1 行、第 2 到 4 列时，播放 `touch_head`。

行为类型：

| 类型 | 说明 |
| --- | --- |
| `none` | 什么都不做 |
| `move_window` | 拖动桌宠窗口 |
| `press_mode` | 按住时播放某个动作，松开后恢复 |
| `switch_mode` | 切换到某个动作 |

## move_settings.json：自动移动配置

`config/move_settings.json` 控制桌宠的自动移动

| 字段 | 说明 |
| --- | --- |
| `enabled_default` | 默认是否开启自动移动 |
| `interval_min_ms` | 两次移动之间的最短间隔 |
| `interval_max_ms` | 两次移动之间的最长间隔 |
| `tick_ms` | 移动刷新间隔，通常不用改 |
| `moves` | 自动移动可选动作列表 |
| `boundary_px` | 桌宠可以靠近屏幕边缘的范围 |
| `distance_min_px` | 单次移动的最低距离 |

注意事项：`mode` 必须是一个已注册动作，通常要选带方向感的动作，比如 `walk_left`、`crawl_right`、`climb_left`。

## window_settings.json：窗口配置和开发模式开关

`config/window_settings.json` 开发模式开关，记录桌宠窗口大小、位置、UI 窗口位置。

| 字段 | 说明 |
| --- | --- |
| `display_size` | 桌宠显示尺寸 |
| `display_x` | 桌宠窗口横向位置 |
| `display_y` | 桌宠窗口纵向位置 |
| `dev_mode` | 是否显示开发调试信息 |
| `ui_windows` | 养成相关 UI 窗口的位置和大小记录 |

`ui_windows` 目前包含两个子窗口：

| 字段 | 说明 |
| --- | --- |
| `ui_windows.activity` | 活动选择窗口的 x、y、width、height |
| `ui_windows.shop_inventory` | 商店 / 背包窗口的 x、y、width、height |

如果桌宠跑到看不见的位置，可以关掉桌宠后手动改 `display_x` 和 `display_y`。

## activity_settings.json：活动配置

`config/activity_settings.json` 定义桌宠可以执行的各种活动，比如工作赚钱、学习积累经验、运动保持健康、休息恢复状态、日常互动提升好感。

每个活动包含以下字段：

| 字段 | 说明 |
| --- | --- |
| `id` | 活动唯一标识，用于内部引用 |
| `name` | 活动在菜单里显示的中文名 |
| `category` | 活动分类，比如"工作"、"学习"、"运动"、"休息"、"日常互动" |
| `duration_seconds` | 活动持续时长，单位秒 |
| `description` | 活动简短说明 |
| `requirements` | 开始活动需要达到的最低状态值（`energy` / `mood` / `health`） |
| `animation_id` | 活动期间播放的动作 id，必须在 `modes.json` 里注册 |
| `animation_candidates` | 可选，动画候选列表，桌宠会从中随机选择 |
| `costs` | 执行活动消耗的状态值（`energy` / `mood` 等） |
| `rewards` | 完成后获得的奖励（`money` / `exp` / `mood` / `health` / `affection`） |

例子：

```json
{
  "id": "work_cleaning",
  "name": "擦擦屏幕",
  "category": "工作",
  "duration_seconds": 900,
  "description": "接一份短委托，消耗体力和心情换取金币。",
  "requirements": {
    "energy": 30,
    "mood": 20,
    "health": 25
  },
  "animation_id": "work_clean",
  "costs": {
    "energy": 16,
    "mood": 8
  },
  "rewards": {
    "money": 30
  }
}
```

注意事项：
- `animation_id` 和 `animation_candidates` 里引用的动作必须已在 `modes.json` 注册。
- `requirements` 里的状态值不满足时，活动不会出现在菜单里。
- 没有 `animation_candidates` 时，桌宠使用 `animation_id` 指定的动作。

## item_catalog.json：商店物品目录

`config/item_catalog.json` 定义商店里可以购买的所有物品。

每个物品的字段：

| 字段 | 说明 |
| --- | --- |
| `id` | 物品唯一标识 |
| `name` | 物品在商店里显示的中文名 |
| `category` | 物品分类，目前有 `food`（食物）、`drink`（饮料）、`medicine`（药品）、`cleaning`（清洁）、`gift`（礼物） |
| `icon` | 物品图标文件名，对应素材目录里的 PNG |
| `price` | 购买价格，单位金币 |
| `effects` | 使用后的效果，可包含 `satiety`（饱腹度）、`mood`（心情）、`energy`（体力）、`health`（健康）、`cleanliness`（清洁度）、`affection`（亲密度） |
| `description` | 物品简短说明 |

例子：

```json
{
  "id": "rice_ball",
  "name": "饭团",
  "category": "food",
  "icon": "rice_ball.png",
  "price": 12,
  "effects": {
    "satiety": 24,
    "mood": 2
  },
  "description": "简单又顶饱的食物。"
}
```

注意事项：
- `category` 决定物品出现在商店的哪个分类页签。
- `effects` 里只需要写这个物品实际有效的属性，不需要把六个属性都写上。
- `icon` 图片需要放在对应的素材目录里。

## app_settings.json：应用全局设置

`config/app_settings.json` 是应用级别的全局配置。

| 字段 | 说明 |
| --- | --- |
| `save_location` | 存档存放位置 |

`save_location` 目前支持：

| 值 | 含义 |
| --- | --- |
| `"project_root"` | 存档放在项目根目录（`VPet_for_mac/`），方便开发调试 |

### 存档位置说明

默认是 `"project_root"`，存档文件直接落在项目根目录里，方便开发时随时查看和修改。

如果只是自己玩，建议把存档放到 macOS 标准的应用数据目录，这样升级桌宠或重新拉代码时不会误删存档。macOS 下标准路径是：

```text
~/Library/Application Support/VPet/
```

## 新增一个动作的最小流程

**⬆️除非你愿意手改 json 不然我还是建议这一块直接使用编辑器编辑更直观方便**

1. 在 `assets/animations/` 下新建动作目录。
2. 按 [ASSETS.md](ASSETS.md) 的规则放入图片帧。
3. 在 `config/modes.json` 里注册这个动作。
4. 如果希望它自动出现，把动作 id 加到 `config/action_settings.json` 的对应列表里。
5. 如果希望鼠标触发它，把动作 id 写到 `config/interaction_map.json` 的某个区域里。
6. 重新启动桌宠。

例：新增一个循环待机动作 `wave_hand`。

首先需要在 `assets` 下的对应位置放置帧素材，例如：

```text
assets/animations/wave_hand/normal/loop/01/main/_000_125.png
assets/animations/wave_hand/normal/loop/01/main/_001_125.png
assets/animations/wave_hand/normal/loop/01/main/_002_125.png
```

`modes.json` 增加：

```json
{
  "id": "wave_hand",
  "title": "挥手",
  "type": "loop"
}
```

如果想让它空闲时随机出现，再把 `wave_hand` 加到 `auto_idle_modes`。
