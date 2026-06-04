# 插件配置指南

主要内容：怎么开关插件、每个插件配置大概能改什么。。

## 插件开关

插件是否加载由 `config/plugin_loader.json` 控制。

```json
{
  "plugins": [
    "show_sticker",
    "eat_files",
    "music_dance",
    "tomato_clock"
  ]
}
```

数组里的名字就是要加载的插件。想临时关闭某个插件，就把它从数组里移除。

例如只保留贴纸和番茄钟：

```json
{
  "plugins": [
    "show_sticker",
    "tomato_clock"
  ]
}
```

## 插件自己的配置

每个插件的详细配置放在：

```text
config/plugin_config/
```

当前已有：

| 文件 | 插件 | 用来改什么 |
| --- | --- | --- |
| `show_sticker.json` | 自动发表情 | 表情列表、出现间隔、显示位置、显示大小 |
| `eat_files.json` | 吃文件 | 吃文件动画、废纸篓路径 |
| `music_dance.json` | 随音乐跳舞 | 音量阈值、舞蹈动作、单次动画插入概率 |
| `tomato_clock.json` | 番茄钟 | 工作/休息时长、计时器位置、动作分组 |

## show_sticker：自动发表情

配置文件：

```text
config/plugin_config/show_sticker.json
```

| 字段 | 说明 |
| --- | --- |
| `enabled` | 是否启用 |
| `stickers` | 可随机显示的贴纸 id 列表 |
| `interval_min_ms` | 两次贴纸之间的最短间隔 |
| `interval_max_ms` | 两次贴纸之间的最长间隔 |
| `display_duration_ms` | 单个贴纸显示多久 |
| `size_ratio` | 贴纸相对桌宠大小的比例 |
| `position_x` | 贴纸横向位置比例 |
| `position_y` | 贴纸纵向位置比例 |


## eat_files：吃文件

配置文件：

```text
config/plugin_config/eat_files.json
```

| 字段 | 说明 |
| --- | --- |
| `enabled` | 是否启用 |
| `single_animation` | 吃文件时播放的 `single` 动作 |
| `trash_path` | 文件最后移动到哪里，默认是 `~/.Trash` |

`single_animation` 对应的动作必须在 `config/modes.json` 里注册为 `single`，并且在当前状态下有可播放素材。

文件图标叠在动画上的位置、大小、显示区间等参数直接复用 care_overlay.json 中 "eat" 的配置，不再放在插件配置中。

## music_dance：随音乐跳舞

配置文件：

```text
config/plugin_config/music_dance.json
```

| 字段 | 说明 |
| --- | --- |
| `enabled` | 是否启用 |
| `start_threshold` | 音量超过这个值时开始跳舞 |
| `stop_threshold` | 音量低于这个值时停止跳舞 |
| `phased_modes` | 可选舞蹈动作列表 |
| `phased_loop_min` | 每次舞蹈最少循环次数 |
| `phased_loop_max` | 每次舞蹈最多循环次数 |
| `single_modes` | 跳舞中可插入的单次动作 |
| `single_insert_chance` | 插入单次动作的概率 |
| `single_repeat_min` | 单次动作最少重复次数 |
| `single_repeat_max` | 单次动作最多重复次数 |

`phased_modes` 里的动作一定要是 `phased`，`single_modes` 里的动作一定要是 `single`。

## tomato_clock：番茄钟

配置文件：

```text
config/plugin_config/tomato_clock.json
```

| 字段 | 说明 |
| --- | --- |
| `default_group` | 默认动作分组 |
| `default_mode` | 默认工作动作 |
| `default_focus_minutes` | 默认专注分钟数 |
| `default_rest_minutes` | 默认休息分钟数 |
| `focus_minutes` | 专注时长可选项 |
| `rest_minutes` | 休息时长可选项 |
| `rest_mode` | 休息时播放的动作 |
| `timer_window_y_offset_px` | 计时器窗口纵向偏移 |
| `timer_window_move_step_px` | 计时器窗口微调步长 |
| `groups` | 菜单里的动作分组 |

动作分组例子：

```json
{
  "groups": {
    "study": {
      "title": "学习",
      "modes": [
        "study",
        "study_two",
        "calligraphy",
        "study_paint"
      ]
    }
  }
}
```

`groups.*.modes` 里的动作都应该是适合长时间播放的 `loop` 或 `phased` 动作。

## 插件开发约定

如果要新增插件，至少下面这几个地方要对上。

### 1. 插件文件名

插件名写在 `config/plugin_loader.json` 里，例如：

```json
{
  "plugins": [
    "show_sticker"
  ]
}
```

对应文件：

```text
plugins/show_sticker.py
```

如果插件是目录形式，也可以是：

```text
plugins/eat_files/plugin.py
```

### 2. 插件类名

插件类名使用大驼峰加 `Plugin`。

```text
show_sticker -> ShowStickerPlugin
music_dance -> MusicDancePlugin
tomato_clock -> TomatoClockPlugin
```

### 3. 插件基础接口

等我后续再补。。

## 注意事项

1. 改完配置要重启桌宠，多数配置是在插件启动时读取的，不会实时刷新
