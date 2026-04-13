# 我想给她在 Mac 上完整的一生喵

![喵](https://imageshostneko.nekostep.cn/PicGo/2026/04/fe5a60c2bde22c92459ab59161a3d5c4.png)

mac 上怎么能没有桌宠？😡不行不行！🙅‍♀️
能在桌面上待着、发呆、被摸头、跟着音乐乱跳，这样就差不多够了喵。

---

## 你也想玩怎么办

直接去 Release 里下载打包好的 `VPet_for_mac.app` 就可以了喵。

不过现在还没有 Apple Developer 正式签名，所以第一次打开时，macOS 大概率会拦一下喵。

可以这样打开喵：

- 在访达里找到 `VPet_for_mac.app`喵
- 右键应用，选择“打开”喵
- 如果系统还拦着，就去“系统设置 -> 隐私与安全性”里允许打开喵

如果系统提示“App 已损坏”或者还是打不开，可以在终端里执行这句喵：

```bash
xattr -dr com.apple.quarantine VPet_for_mac.app
```

默认配置文件会在第一次运行后自动生成到这里喵：

```text
~/Library/Application Support/VPet_for_mac/config/
```

## 你想整个 clone 下来自己玩怎么办

先在项目目录里创建并启用虚拟环境喵：

```bash
python3.12 -m venv .venv
source .venv/bin/activate
```

然后安装依赖喵：

```bash
pip install -r requirements.txt
pip install pyinstaller
```

执行一下导出脚本就可以开始编译喵：

```bash
./.venv/bin/python export.py
```

编译完成后，大概会输出到这里喵：

```text
export/VPet_for_mac.app
```

---

## TodoList

- [x] 可以随意拖动
- [x] 可以实现放大缩小
- [x] 记忆退出位置与大小
- [x] 可以切换动作
- [x] 添加切换小标，切换鼠标穿透模式
- [x] 自动切换待机动作
- [x] 实现摸头等互动动作
- [x] 随音乐跳舞
- [x] 启动和退出动画
- [ ] 桌宠自动发送表情
- [ ] 自动移动
- [ ] 互动列表，睡觉，学习，工作等，自带计时器
- [ ] 桌宠状态更新，保存存档
- [ ] 桌宠对话，自动说话聊天
- [ ] 桌宠接入大模型实现对话

剩下的这些有一说一不一定全会做喵。
她只需要在桌面上可爱就够了喵。

---

## 动画文件来源

[虚拟桌宠模拟器](https://github.com/LorisYounger/VPet)
