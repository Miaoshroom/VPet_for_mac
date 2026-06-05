# 桌宠 AI 聊天功能说明

主要内容：桌宠萝莉斯的 AI 聊天功能，包括对话、贴纸、AI 动作、长期记忆、自定义配置等。

## 能做什么

- 与桌宠聊天，桌宠会以萝莉斯的口吻简短回复
- 发送贴纸表情，桌宠也能回复贴纸
- 桌宠回复时可触发动画动作（自言自语、严肃说话、发光说话、害羞说话）
- 通过对话让桌宠帮忙使用背包物品（饭团、汽水、药品等）
- 用自然语言告诉桌宠"记住 xxx"，写入长期记忆
- 用自然语言让桌宠"忘记 xxx"，删除长期记忆
- 打开长期记忆编辑面板，手动查看和修改记忆 JSON
- 加载历史聊天记录，向上滚动查看更早的对话
- 配置桌宠性格、用户偏好、对话风格规则

## 如何打开

**从桌宠状态面板打开**：点击桌宠右下角状态面板中的聊天按钮，点击聊天窗口以外的地方会自动关闭。

## 界面说明

| 区域 | 说明 |
| --- | --- |
| 消息列表 | 显示双方消息，支持向上滚动加载历史记录 |
| 头像 | 用户头像（`resources/chat/user_default_avatar.png`）和桌宠头像（`resources/chat/pet_default_avatar.png`） |
| 输入栏 | 底部输入框 + 发送按钮 |
| 关闭按钮 | 输入栏右上角 × 按钮 |
| 加号菜单 | 输入栏左下角 + 按钮，可打开贴纸选择器或长期记忆编辑面板 |
| 贴纸选择器 | 从用户贴纸目录或配置中选择贴纸发送 |
| 长期记忆编辑面板 | 以 JSON 编辑器查看和修改长期记忆全文 |

## 对话功能

### 基本聊天

在输入框打字，回车或点击发送按钮。桌宠会以萝莉斯的人设简短回复，风格由多份配置文件共同控制。

桌宠回复时会自动选择一个匹配语气的动画动作（四选一）：

| 动作 id | 说明 |
| --- | --- |
| `say_self` | 自言自语 |
| `say_serious` | 严肃说话 |
| `say_shining` | 发光说话 |
| `say_shy` | 害羞说话 |

这些动作需要在 `assets/animations/` 下有对应的素材才能播放。

### 贴纸

桌宠和用户都可以发送贴纸。贴纸来源有两个：

1. **配置的桌宠贴纸**：在 `config/chat/pet_stickers.json` 中注册，图片放在 `chat_data/pet_stickers/` 下
2. **用户自定义贴纸**：直接把 PNG/WebP/GIF/JPG 图片放到 `chat_data/user_stickers/` 目录下，文件名（不含扩展名）即为贴纸 id

在加号菜单中选择贴纸，或在贴纸选择器中点击贴纸发送。桌宠偶尔也会用贴纸回复。

### AI 动作效果

桌宠可以在回复的同时请求播放一个动画动作。这些动作受安全限制：必须是 `single` 或 `phased` 类型、必须在 `ai_actions.json` 中启用、必须有当前桌宠状态对应的素材。

如果桌宠正在忙（自动移动、活动、养成播放中等），动作请求会被拒绝。

### 物品使用请求

用户可以请桌宠使用背包里的物品，桌宠会生成 `use_item` 请求。允许的物品 id 在 `config/chat/ai_actions.json` 的 `allowed_use_item_ids` 中配置。

## 长期记忆

### 显式记忆命令

在聊天中直接告诉桌宠记住或忘记某些事。系统通过正则匹配识别这些命令，不经过 AI。

**写入记忆**（以下句式均可触发）：

- "帮我记住 xxx"
- "记住 xxx"
- "记一下 xxx"
- "以后记得 xxx"
- "这件事帮我记住 xxx"

示例：`帮我记住我不喜欢太甜的食物` → 写入长期记忆的 `manual_notes`

注意：
- 显式记忆命令中的"我"会自动转换为"用户"存储
- 敏感凭据（API key、token、password 等）会被拒绝写入
- 至少需要 3 个字的有效内容
- 重复的记忆内容会自动去重

**删除记忆**（以下句式均可触发）：

- "忘记 xxx"
- "删除关于 xxx 的记忆"
- "不要记得 xxx"
- "把 xxx 从记忆里删掉"

如果匹配到单条记忆，系统会弹出确认对话框；匹配到多条会提示去记忆面板手动确认；匹配到 0 条会提示找不到。

**安全限制**：
- 不支持"清空全部记忆"命令
- 不能删除 user_profile、pet_persona、API 设置等受保护内容
- 长期记忆本身不能通过 AI 回复修改，只能由用户手动编辑或通过显式命令操作

### 长期记忆编辑面板

从加号菜单 → 长期记忆，打开 JSON 编辑面板。这里显示完整的长期记忆 JSON，可以手动编辑后保存。保存时会自动创建备份到 `chat_data/memory/backups/`。

长期记忆结构：

| 字段 | 说明 |
| --- | --- |
| `relationship_summary` | 关系摘要 |
| `user_preferences` | 用户偏好列表 |
| `important_facts` | 重要事实 |
| `recurring_topics` | 经常聊到的话题 |
| `boundaries` | 边界设定 |
| `manual_notes` | 手动添加的备注 |
| `daily_summaries` | 每日对话摘要 |

注意：AI 只能读取长期记忆的裁剪摘要，不能修改。

## 配置文件

所有聊天配置文件位于 `config/chat/` 目录下。缺失任何文件时系统会使用内置默认值，不会自动创建配置文件。

### ai_settings.json：AI 服务设置

```json
{
  "schema_version": 1,
  "provider": "deepseek",
  "model": "deepseek-chat",
  "api_key_env": "DEEPSEEK_API_KEY",
  "api_key_file": "config/chat/api_key.local.json",
  "timeout_seconds": 30,
  "retries": 1,
  "temperature": 0.7,
  "max_tokens": 800
}
```

| 字段 | 说明 | 默认值 |
| --- | --- | --- |
| `provider` | AI 提供方，目前支持 `"deepseek"` 和 `"fake"`（离线测试假回复） | `"fake"` |
| `model` | 模型名称，传给 API | `"deepseek-chat"` |
| `api_key_env` | 从环境变量读取 API Key 的变量名（如 `DEEPSEEK_API_KEY`） | `"DEEPSEEK_API_KEY"` |
| `api_key_file` | 从 JSON 文件读取 API Key 的路径，优先级高于 `api_key_env` | `"config/chat/api_key.local.json"` |
| `timeout_seconds` | API 请求超时时间（秒） | `30` |
| `retries` | 请求失败后的重试次数 | `1` |
| `temperature` | 模型温度参数（0.0 ~ 2.0），越高越随机 | `0.7` |
| `max_tokens` | 模型最大输出 token 数 | `800` |

**设置 API Key**：

方式一（推荐）：复制 `config/chat/api_key.example.json` 为 `config/chat/api_key.local.json`，然后填入 API Key：

```json
{
  "schema_version": 1,
  "deepseek_api_key": "sk-xxxxxxxxxxxxxxxx"
}
```

`api_key.local.json` 已被 `.gitignore` 忽略，不会提交到版本控制。

方式二：设置环境变量 `DEEPSEEK_API_KEY`（或 `api_key_env` 中配置的变量名）。

API Key 的查找优先级：`api_key_file` > `api_key_env`。

**切换提供方**：

将 `provider` 改为 `"deepseek"` 使用 DeepSeek API；改为 `"fake"` 使用本地假回复（不需要 API Key，固定回复"嗯嗯"）。后续可通过实现 `ChatProvider` 协议接入其他 AI 服务。

### pet_persona.json：桌宠人设

定义桌宠的名字、性格、语气、说话习惯、边界等。

| 字段 | 说明 |
| --- | --- |
| `name` | 桌宠名字，默认"萝莉斯" |
| `summary` | 人设一句话概括 |
| `relationship` | 与用户的关系描述 |
| `address_user` | 对用户的称呼 |
| `self_references` | 自称方式（如"我"、"人家"） |
| `tone` | 语气关键词列表 |
| `speech_habits` | 说话习惯规则 |
| `comfort_style` | 安慰用户时的风格 |
| `nudge_style` | 提醒/催用户时的风格 |
| `never_say` | 禁止说的话（如客服腔、AI 套话） |
| `boundaries` | 行为边界（不能修改养成状态等） |

完整示例见 `config/chat/pet_persona.json`。

### user_profile.json：用户资料

定义用户偏好，影响桌宠的对话风格。

| 字段 | 说明 |
| --- | --- |
| `display_name` | 显示名称 |
| `preferred_name` | 偏好称呼 |
| `preferred_pronouns` | 偏好代词 |
| `pet_call_user` | 桌宠对用户的称呼，默认"主人" |
| `relationship_to_pet` | 与桌宠的关系 |
| `chat_preferences` | 对话偏好：`reply_length`（回复长度）、`comfort_style`（安慰风格）、`teasing_level`（吐槽尺度）、`advice_style`（建议风格）、`emoji_or_sticker_preference`（emoji/贴纸偏好） |
| `boundaries` | 用户边界：`avoid_topics`（避开话题）、`avoid_tone`（避开语气）、`never_call_user`（禁止称呼） |
| `profile_editing` | 资料编辑控制：`ai_may_modify` 必须为 `false`，AI 不能修改用户资料 |
| `notes` | 人工备注 |

完整示例见 `config/chat/user_profile.json`。

### prompt_rules.json：对话规则

控制 AI 的回复行为、允许的动作、禁止的操作等。

| 字段 | 说明 |
| --- | --- |
| `conversation_goal` | 对话目标描述 |
| `style_rules` | 风格规则列表，每条一个约束（默认 25 条规则） |
| `allowed_state_requests` | 允许的状态请求类型，目前只有 `"use_item"` |
| `forbidden_requests` | 禁止的请求类型列表（如删除历史、修改记忆、修改养成状态等） |
| `response_schema` | AI 回复必须遵守的 JSON schema |

完整示例见 `config/chat/prompt_rules.json`。

### ai_actions.json：可用动作和物品

定义 AI 可以请求的动画动作和允许使用的物品。

```json
{
  "schema_version": 1,
  "actions": [
    {"id": "say_self", "label": "自言自语", "allow_in_v1": true},
    {"id": "say_serious", "label": "严肃说话", "allow_in_v1": true},
    {"id": "say_shining", "label": "发光说话", "allow_in_v1": true},
    {"id": "say_shy", "label": "害羞说话", "allow_in_v1": true}
  ],
  "allowed_use_item_ids": [
    "rice_ball", "sparkling_water", "basic_medicine",
    "cleaning_wipes", "gift_box"
  ]
}
```

| 字段 | 说明 |
| --- | --- |
| `actions[].id` | 动作 id，必须对应 `assets/animations/<id>` 和 `modes.json` 中的注册 |
| `actions[].label` | 显示标签 |
| `actions[].allow_in_v1` | 是否在 v1 中启用 |
| `allowed_use_item_ids` | 桌宠可通过对话请求使用的物品 id 列表，必须对应 `item_catalog.json` 中的物品 |

### pet_stickers.json：桌宠贴纸配置

```json
{
  "schema_version": 1,
  "stickers": [
    {
      "id": "坏笑",
      "label": "坏笑",
      "metadata": {
        "path": "chat_data/pet_stickers/坏笑.png",
        "tags": ["teasing", "playful"],
        "scenarios": ["轻微吐槽", "调皮回应"]
      }
    }
  ]
}
```

| 字段 | 说明 |
| --- | --- |
| `id` | 贴纸唯一标识，也是文件名（不含扩展名） |
| `label` | 贴纸显示标签和发给 AI 的描述 |
| `metadata.path` | 可选，贴纸图片的显式路径 |
| `metadata.tags` | 可选，标签列表，用于帮助 AI 匹配合适的贴纸 |
| `metadata.scenarios` | 可选，使用场景描述 |

### storage.json：存储路径

```json
{
  "schema_version": 1,
  "history_dir": "chat_data/history",
  "memory_dir": "chat_data/memory",
  "pet_stickers_dir": "chat_data/pet_stickers",
  "user_stickers_dir": "chat_data/user_stickers",
  "attachments_dir": "chat_data/attachments",
  "long_term_memory_file": "chat_data/memory/long_term_memory.json",
  "recent_history_days": 7,
  "recent_history_limit": 40
}
```

| 字段 | 说明 |
| --- | --- |
| `history_dir` | 聊天历史存储目录，按天分 JSONL 文件 |
| `memory_dir` | 长期记忆目录 |
| `pet_stickers_dir` | 桌宠贴纸图片目录 |
| `user_stickers_dir` | 用户贴纸图片目录 |
| `attachments_dir` | 附件目录（预留） |
| `long_term_memory_file` | 长期记忆 JSON 文件路径 |
| `recent_history_days` | 加载最近多少天的历史 |
| `recent_history_limit` | 加载最近多少条消息 |

所有相对路径均相对于项目根目录解析。

## 数据目录

聊天运行时会自动创建以下目录结构：

```text
chat_data/
├── history/            # 聊天历史，按天分文件：2026-06-05.jsonl
├── memory/             # 长期记忆 JSON 和备份
│   ├── long_term_memory.json
│   └── backups/        # 每次保存记忆时自动备份
├── pet_stickers/       # 桌宠贴纸图片 (.png/.webp/.gif/.jpg)
├── user_stickers/      # 用户自定义贴纸图片
└── attachments/        # 附件目录（预留）
```

## 自定义贴纸

### 添加桌宠贴纸

1. 将贴纸图片放到 `chat_data/pet_stickers/` 目录（支持 `.png`、`.webp`、`.gif`、`.jpg`、`.jpeg`）
2. 在 `config/chat/pet_stickers.json` 中注册贴纸：

```json
{
  "schema_version": 1,
  "stickers": [
    {
      "id": "happy",
      "label": "开心",
      "metadata": {
        "tags": ["happy", "positive"],
        "scenarios": ["开心的时候", "主人说好消息"]
      }
    }
  ]
}
```

### 添加用户贴纸

直接把图片文件放到 `chat_data/user_stickers/` 目录即可。文件名（不含扩展名）会自动作为贴纸 id 和标签。无需额外配置。

## 自定义桌宠性格

编辑 `config/chat/pet_persona.json`：

- 修改 `name` 改变桌宠名字
- 修改 `tone` 调整语气风格（添加或删除关键词）
- 修改 `speech_habits` 改变说话习惯
- 修改 `never_say` 添加更多禁止语
- 修改 `address_user` 改变桌宠对用户的称呼

编辑 `config/chat/user_profile.json`：

- 修改 `pet_call_user` 改变桌宠怎么叫你
- 修改 `chat_preferences` 调整回复长度、吐槽尺度、建议风格等
- 修改 `boundaries.avoid_topics` 添加不想聊的话题
- 修改 `boundaries.never_call_user` 添加不想被叫的称呼

## 自定义对话风格

编辑 `config/chat/prompt_rules.json` 中的 `style_rules` 数组，可以精细控制 AI 的回复行为。默认已有 25 条规则，可以增减或修改。

示例规则：
- `"日常聊天默认只回一句短句，尽量 5-15 个字。"`
- `"可以偶尔撒娇、吐槽、装可怜，但必须轻一点，不能油腻。"`
- `"不要说自己是 AI、人工智能、模型、助手。"`

## 离线测试模式

将 `config/chat/ai_settings.json` 中的 `provider` 设为 `"fake"` 即可切换到离线测试模式。无需 API Key，桌宠会固定回复"嗯嗯"。适合开发调试或不想使用 AI 服务时使用。

## 技术架构

聊天功能采用离线、非流式架构：

```text
用户输入 → ChatController → ChatService → ContextBuilder（构建请求上下文）
                                          → ChatProvider（调用 AI API）
                                          → ReplyParser（解析 AI 回复）
                                          → HistoryStore（持久化消息）
                       → ChatWindow（更新 UI）
                       → ChatActionEffectExecutor（执行动画效果）
```

核心模块：

| 模块 | 位置 | 说明 |
| --- | --- | --- |
| 配置 | `core/chat/config.py` | 读取和合并所有聊天配置文件 |
| 数据模型 | `core/chat/models.py` | 消息、回复、效果请求等纯数据结构 |
| 服务编排 | `core/chat/service.py` | 一轮对话的完整编排（记忆命令解析 → 上下文构建 → API 调用 → 回复解析 → 持久化） |
| 上下文构建 | `core/chat/context_builder.py` | 构建发给 AI 的完整请求上下文 |
| 记忆管理 | `core/chat/memory_store.py` | 长期记忆的读写、去重、搜索、备份 |
| 记忆命令 | `core/chat/memory_commands.py` | 正则匹配解析显式记忆写入/删除命令 |
| 历史存储 | `core/chat/history_store.py` | 按天分文件的 JSONL 聊天历史 |
| 回复解析 | `core/chat/reply_parser.py` | 从 AI 原始回复中解析结构化 JSON |
| DeepSeek 提供方 | `core/chat/providers/deepseek.py` | DeepSeek API 调用实现 |
| 假提供方 | `core/chat/providers/fake.py` | 离线测试用假回复 |

UI 模块（`ui/chat/`）：

| 组件 | 说明 |
| --- | --- |
| `chat_window.py` | 无边框聊天主窗口 |
| `controller.py` | 聊天窗口控制器，管理消息收发和界面状态 |
| `chat_list.py` | 消息列表组件，支持滚动加载历史 |
| `chat_bubble.py` | 聊天气泡组件 |
| `input_bar.py` | 输入栏组件 |
| `worker.py` | 后台线程 Worker，避免阻塞 UI |
| `plus_menu.py` | 加号菜单 |
| `sticker_picker.py` | 贴纸选择器 |
| `sticker_resolver.py` | 贴纸路径解析 |
| `memory_editor.py` | 长期记忆 JSON 编辑面板 |
| `avatar.py` | 头像渲染 |

## 注意事项

1. JSON 配置文件不能有注释，逗号要严格。
2. `config/chat/api_key.local.json` 已在 `.gitignore` 中忽略，不要提交 API Key。
3. `ai_actions.json` 中引用的动作 id 必须在 `modes.json` 中注册且素材存在。
4. 显式记忆命令匹配的是中文指令格式，不支持英文自然语言命令。
5. AI 只能读取长期记忆的裁剪摘要，不能直接修改 — 写入只能通过显式命令或记忆编辑面板。
6. 在 `provider` 为 `"fake"` 时，所有 AI 相关功能（对话、贴纸、动作）都不会真正调用 AI。
7. `visual_state` 只允许 `happy`、`normal`、`poor_condition`、`ill` 四种；`any` 是素材兜底目录，不能用于 AI 状态。
8. AI 不能修改 `PetState`、`SaveGame`、`user_profile`、`pet_persona`、`api_settings`、历史路径或长期记忆。
