# 动画素材目录规范

主要内容： `assets/animations` 里的素材怎么放。改 JSON 的说明见 [CUSTOMIZATION.md](CUSTOMIZATION.md)。

## 固定路径格式

```text
assets/animations/<动作id>/<状态>/<阶段>/<变体>/<图层>/<图片帧>.png
```

例子：

```text
assets/animations/touch_head/normal/start/01/main/_000_125.png
assets/animations/touch_head/normal/loop/01/main/_000_125.png
assets/animations/touch_head/normal/end/01/main/_000_125.png
```

| 字段 | 规则 |
| --- | --- |
| `动作id` | 动作目录名，例如 `default`、`touch_head`、`walk_left` |
| `状态` | 只能是 `happy`、`normal`、`poor_condition`、`ill`、`any` |
| `阶段` | 只能是 `loop`、`start`、`end`、`single` |
| `变体` | 两位数字，例如 `01`、`02`、`03` |
| `图层` | 只能是 `main`、`back`、`front` |
| `图片帧` | PNG 图片，命名必须包含帧序号和帧延时 |

## 动作 id

动作 id 是连接素材和配置的名字。

如果素材目录是：

```text
assets/animations/touch_head/
```

那么 `config/modes.json` 里也要有：

```json
{
  "id": "touch_head",
  "title": "摸头",
  "type": "phased"
}
```

建议动作 id 只用小写英文、数字和下划线，比如：

```text
touch_head
walk_left
dance_music_1
```

## 状态目录

状态目录表示同一个动作在不同状态下的素材。

允许的状态：

| 状态 | 含义 |
| --- | --- |
| `happy` | 开心状态 |
| `normal` | 普通状态 |
| `poor_condition` | 状态较差 |
| `ill` | 生病状态 |
| `any` | 兜底素材 |

`any` 的用途是兜底：如果当前状态没有素材，桌宠才会尝试使用 `any`。

例如：

```text
assets/animations/meow/any/loop/01/main/_000_125.png
```

这表示 `meow` 可以在任何状态下使用这套素材。

如果同时存在：

```text
assets/animations/meow/any/loop/01/main/_000_125.png
assets/animations/meow/happy/loop/01/main/_000_125.png
```

开心状态下会优先使用 `happy`，其他状态可以继续使用 `any`。

## 阶段目录和动作类型

阶段目录要和 `modes.json` 里的动作类型匹配。

| `modes.json` 的 `type` | 需要的阶段目录 | 说明 |
| --- | --- | --- |
| `loop` | `loop` | 一直循环播放 |
| `phased` | `start`、`loop`、`end` | 先开始，再循环，最后结束 |
| `single` | `single` | 播放一次就结束 |

### loop 动作

适合默认待机、发呆、普通循环动作。

```text
assets/animations/default/normal/loop/01/main/_000_125.png
assets/animations/default/normal/loop/01/main/_001_125.png
```

### phased 动作

适合摸头、睡觉、跳舞这类有完整过程的动作。

```text
assets/animations/touch_head/normal/start/01/main/_000_125.png
assets/animations/touch_head/normal/loop/01/main/_000_125.png
assets/animations/touch_head/normal/end/01/main/_000_125.png
```

`phased` 动作必须能凑出完整的 `start`、`loop`、`end`。如果只有 `loop`，就应该把动作类型写成 `loop`。

### single 动作

适合启动、退出、升级、临时插入的小动画。

```text
assets/animations/shutdown/normal/single/01/main/_000_125.png
assets/animations/shutdown/normal/single/01/main/_001_125.png
```

## 变体目录

变体用于给同一个动作准备多个版本。目录名必须是两位数字。

```text
loop/01/main/_000_125.png
loop/02/main/_000_125.png
loop/03/main/_000_125.png
```
桌宠会从可播放的变体里随机选一个。

## 分段动画

如果只有 `loop` 有多个变体，只需要增加 `loop/02`、`loop/03`。桌宠选择到某个 loop 变体后，可以优先找同编号的 `start` 和 `end`，找不到就回退到 `start/01` 和 `end/01`。

```text
assets/animations/touch_head/normal/start/01/main/_000_125.png
assets/animations/touch_head/normal/loop/01/main/_000_125.png
assets/animations/touch_head/normal/loop/02/main/_000_125.png
assets/animations/touch_head/normal/end/01/main/_000_125.png
```

如果你希望 `loop/02` 有专属开始和结束，可以这样放：

```text
assets/animations/touch_head/normal/start/02/main/_000_125.png
assets/animations/touch_head/normal/loop/02/main/_000_125.png
assets/animations/touch_head/normal/end/02/main/_000_125.png
```

## 图层目录

图层目录只能使用：

```text
back
main
front
```

绘制顺序是：

```text
back -> main -> front
```

普通动画只放 `main` 就够了。

```text
assets/animations/default/normal/loop/01/main/_000_125.png
```

如果要做分层动画，可以把背景、主体、前景拆开：

```text
assets/animations/example/normal/loop/01/back/_000_125.png
assets/animations/example/normal/loop/01/main/_000_125.png
assets/animations/example/normal/loop/01/front/_000_125.png
```

分层时，每个图层都有自己的帧延时。桌宠会按时间线合成画面。

## 图片命名

图片命名保留帧序号和单帧延时：

```text
_000_125.png
_001_125.png
idle_002_250.png
```

最后两个数字的含义：

- 帧序号：`000`、`001`、`002`
- 单帧显示时间，单位毫秒：`125`、`250`

完整规则：

```text
任意前缀_<帧序号>_<帧延时毫秒>.png
```

例如：

```text
sleep_000_125.png
sleep_001_125.png
sleep_002_250.png
```

注意：

- 必须是 `.png`。
- 帧延时必须大于 0。
- 同一个图层里帧序号不能重复。
- 桌宠按帧序号排序，不按文件系统显示顺序排序。

## 替换已有素材

我直接稳稳的接住你：

1. 找到要替换的动作目录。
2. 保持原来的目录层级不变。
3. 保持文件命名规则不变。
4. 用新的 PNG 覆盖旧 PNG。
5. 重新启动桌宠。

例子：替换普通状态下的摸头循环帧。

```text
assets/animations/touch_head/normal/loop/01/main/
```

只要新图片仍然叫：

```text
_000_125.png
_001_125.png
_002_125.png
```

桌宠就会按原规则读取。

## 新增一个 loop 动作

目录：

```text
assets/animations/wave_hand/normal/loop/01/main/_000_125.png
assets/animations/wave_hand/normal/loop/01/main/_001_125.png
assets/animations/wave_hand/normal/loop/01/main/_002_125.png
```

然后在 `config/modes.json` 里注册：

```json
{
  "id": "wave_hand",
  "title": "挥手",
  "type": "loop"
}
```

如果想让它空闲时随机出现，再把 `wave_hand` 加到 `config/action_settings.json` 的 `auto_idle_modes`。

## 新增一个 phased 动作

目录：

```text
assets/animations/read_book/normal/start/01/main/_000_125.png
assets/animations/read_book/normal/loop/01/main/_000_125.png
assets/animations/read_book/normal/end/01/main/_000_125.png
```

然后在 `config/modes.json` 里注册：

```json
{
  "id": "read_book",
  "title": "读书",
  "type": "phased"
}
```

`phased` 动作至少要保证 `start/01`、`loop/01`、`end/01` 都能播放。

## 新增一个 single 动作

目录：

```text
assets/animations/hello/normal/single/01/main/_000_125.png
assets/animations/hello/normal/single/01/main/_001_125.png
```

然后在 `config/modes.json` 里注册：

```json
{
  "id": "hello",
  "title": "打招呼",
  "type": "single"
}
```

如果想让它启动时播放，把 `hello` 加到 `config/action_settings.json` 的 `startup`。如果想让它空闲时偶尔插入，把它加到 `single_insert_modes`。

## 注意事项

1. 目录里不要多放别的文件

2. 变体必须是两位数字

3. phased 动作不能缺阶段