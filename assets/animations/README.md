# 动画素材目录规范

固定路径格式：

```text
assets/animations/<动作>/<状态>/<阶段>/<变体>/<图层>/<图片帧>
```

字段说明：

- `动作`：动画动作 ID，统一使用小写英文和下划线，例如 `default`、`touch_head`、`walk_left`。
- `状态`：桌宠动画状态，只使用 `happy`、`normal`、`poor_condition`、`ill`、`any`。
- `阶段`：播放阶段，只使用 `loop`、`start`、`end`、`single`。
- `变体`：同一个动作、状态、阶段、图层下的不同版本，统一使用两位数字，例如 `01`、`02`、`03`。
- `图层`：普通动画使用 `main`；分层动画使用 `back` 和 `front`。

## 分段动画

如果只有 `loop` 有多个变体，只需要增加 `loop/02`、`loop/03`。程序选择到某个 loop 变体后，可以优先找同编号的 `start` 和 `end`，找不到就回退到 `start/01` 和 `end/01`。

```text
assets/animations/touch_head/normal/start/01/main/_000_125.png
assets/animations/touch_head/normal/loop/01/main/_000_125.png
assets/animations/touch_head/normal/loop/02/main/_000_125.png
assets/animations/touch_head/normal/end/01/main/_000_125.png
```

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
