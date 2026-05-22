# Feishu Local Agent

本地运行的飞书 AI Agent：通过 `lark-cli event consume` 监听飞书机器人消息，调用 LLM 生成回复，再用 `lark-cli im +messages-reply` 回复到飞书。

## 工作原理

```
飞书用户发消息 → 飞书服务器 → lark-cli event consume（子进程）
    → feishu_agent.py 解析事件 → 调用 LLM API → lark-cli im +messages-reply → 飞书
```

支持两种 LLM API 格式：
- **Anthropic 格式**：当 `LLM_BASE_URL` 包含 `anthropic` 时自动切换（如小米 MiMo）
- **OpenAI 格式**：默认使用 `/chat/completions` 接口

## 项目结构

```
feishu-agent/
├── feishu_agent.py   # 主程序，单文件，无第三方依赖
├── .env.example      # 环境变量模板
├── .env              # 实际配置（不提交到 Git）
├── .gitignore
└── README.md
```

## 快速开始

### 第 1 步：安装 lark-cli

**环境要求**：Node.js（npm/npx）、Python 3.9+

```bash
# 安装 CLI
npm install -g @larksuite/cli

# 安装 CLI Skill（必需，会注册飞书相关命令）
npx -y skills add https://open.feishu.cn --skill -y
```

安装完成后验证：

```bash
lark-cli --version
```

> 如果已有 lark-cli，可通过 `lark-cli update` 检查并更新到最新版本。

### 第 2 步：创建飞书应用

1. 打开 [飞书开发者后台](https://open.feishu.cn/app)，创建一个**企业自建应用**
2. 在「凭证与基础信息」页面，记录下 **App ID** 和 **App Secret**
3. 进入「添加应用能力」，开启 **机器人** 能力
4. 进入「事件与回调」→「事件配置」：
   - 添加事件订阅 `im.message.receive_v1`（接收消息）
   - 接收方式选择 **长连接**（无需公网 IP 和域名）
5. 进入「权限管理」，开通以下权限：
   - `im:message` — 获取与发送单聊、群组消息
   - `im:message:send_as_bot` — 以机器人身份发送消息
   - `im:chat:readonly` — 获取群组信息
6. 发布应用：
   - **测试模式**：在「版本管理与发布」中创建版本，添加测试企业/测试用户后即可使用
   - **正式发布**：创建版本并提交审核，审核通过后全员可用

### 第 3 步：配置 lark-cli 凭证

```bash
lark-cli config init --new
```

按提示输入第 2 步获取的 App ID 和 App Secret。

### 第 4 步：登录授权

```bash
lark-cli auth login --recommend
```

终端会输出一个授权链接，在浏览器中打开并完成授权。登录成功后验证：

```bash
lark-cli auth status
```

确认 `bot` 和 `user` 两个身份状态均为 `ready`。

### 第 5 步：克隆项目并配置

```bash
git clone https://github.com/unsetbad/feishu-agent.git
cd feishu-agent
cp .env.example .env
```

编辑 `.env`，填入你的 LLM API 配置：

```bash
LLM_BASE_URL=https://your-api-endpoint/v1
LLM_API_KEY=your-api-key
LLM_MODEL=your-model-name
```

### 第 6 步：启动

```bash
python3 feishu_agent.py
```

启动成功后会显示：

```
[2026-05-22 16:12:28] Starting Feishu local agent... (API=Anthropic, model=mimo-v2.5-pro)
```

### 第 7 步：测试

- **私聊**：在飞书中搜索你的机器人名称，直接发消息
- **群聊**：将机器人添加到群组，然后 @机器人 发消息

机器人收到消息后会自动回复，终端会打印处理日志：

```
[2026-05-22 16:12:30] received message om_xxx
[2026-05-22 16:12:32] replied to om_xxx (2.1s)
```

## 配置参考

### 必填项

| 变量 | 说明 |
|------|------|
| `LLM_BASE_URL` | LLM API 地址（兼容 `OPENAI_BASE_URL`） |
| `LLM_API_KEY` | API Key（兼容 `OPENAI_API_KEY`） |
| `LLM_MODEL` | 模型名称（兼容 `OPENAI_MODEL`），默认 `gpt-4o-mini` |

### 可选项

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `AGENT_SYSTEM_PROMPT` | 你是一个在飞书里工作的 AI 助手... | 机器人系统提示词 |
| `AGENT_TEMPERATURE` | 0.3 | 生成温度 |
| `AGENT_MAX_TOKENS` | 1200 | 单次最大生成 token 数 |
| `FEISHU_REPLY_FORMAT` | `markdown` | 回复格式，`markdown` 或 `text` |
| `FEISHU_REPLY_MAX_CHARS` | 4000 | 单条回复最大字符数 |
| `FEISHU_REPLY_IN_THREAD` | false | 设为 `true` 时在消息线程里回复 |
| `FEISHU_EVENT_DEDUP_TTL_SECONDS` | 3600 | 事件去重保留时间（秒） |
| `FEISHU_RESTART_DELAY_SECONDS` | 5 | 事件消费器异常退出后的重启间隔（秒） |
| `FEISHU_IGNORE_SENDER_IDS` | 无 | 逗号分隔的 sender open_id，用于忽略指定发送者 |

> `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL` 是新命名，同时兼容旧的 `OPENAI_BASE_URL` / `OPENAI_API_KEY` / `OPENAI_MODEL`，优先读取 `LLM_*`。

### 已测试的 LLM 服务

| 服务 | `LLM_BASE_URL` | `LLM_MODEL` |
|------|----------------|-------------|
| 小米 MiMo | `https://token-plan-cn.xiaomimimo.com/anthropic` | `mimo-v2.5-pro` |
| OpenAI | `https://api.openai.com/v1` | `gpt-4o-mini` |
| 其他 OpenAI 兼容服务 | 各服务的 API 地址 | 对应模型名 |

## 使用技巧

### 后台运行

推荐使用 `tmux` 保持进程：

```bash
tmux new -s feishu-agent
python3 feishu_agent.py
# Ctrl+B D 脱离会话
# tmux attach -t feishu-agent 重新连接
```

### 停止 Agent

- 终端中按 `Ctrl+C`，Agent 会优雅退出
- 如果在 tmux 中，先 `tmux attach -t feishu-agent` 再按 `Ctrl+C`

### 屏蔽特定用户

如果需要让 Agent 忽略某些用户的消息（比如避免机器人回复自己）：

1. 获取该用户的 open_id：`lark-cli contact +search-user --query "用户名"`
2. 在 `.env` 中配置：`FEISHU_IGNORE_SENDER_IDS=ou_xxxxxx,ou_yyyyyy`

### 自定义机器人人设

修改 `AGENT_SYSTEM_PROMPT` 可以改变机器人的角色和回答风格：

```bash
# 示例：技术问答助手
AGENT_SYSTEM_PROMPT=你是一个资深后端工程师，擅长 Python、Go 和分布式系统。回答要包含代码示例，用中文回复。

# 示例：翻译助手
AGENT_SYSTEM_PROMPT=你是一个翻译助手。用户发什么语言就翻译成另一种语言（中英互译）。只输出翻译结果，不要解释。
```

## 消息处理流程

1. 只处理 `text` 类型消息（图片、文件、卡片等自动忽略）
2. 消息经过去重（同一 event_id 在 TTL 内不重复处理，防止飞书重发导致重复回复）
3. 可通过 `FEISHU_IGNORE_SENDER_IDS` 屏蔽特定用户
4. 支持自动重连：事件消费器异常退出后会自动重启
5. 回复内容超过 `FEISHU_REPLY_MAX_CHARS` 时自动截断

## 安全提示

- `.env` 文件已加入 `.gitignore`，不会被提交到 Git 仓库
- 请勿将 API Key 和 App Secret 分享给他人或提交到公开仓库
- 建议定期更换 API Key
- lark-cli 的登录 token 本地存储，refresh token 有效期 7 天，过期需重新登录

## 常见问题

| 问题 | 排查方式 |
|------|----------|
| 收不到消息 | 确认机器人已被添加到群聊；确认应用已发布或当前用户在测试名单中 |
| 权限不足 | 在飞书开发者后台开通缺失的 scope，然后执行 `lark-cli auth login --recommend` 重新授权 |
| 模型报错 401 | API Key 无效或过期，检查 `LLM_API_KEY` |
| 模型报错 404 | API 地址错误，检查 `LLM_BASE_URL` 路径是否正确 |
| Anthropic 接口 404 | 确认 `LLM_BASE_URL` 以 `/anthropic` 结尾（如小米 MiMo） |
| 回复格式错乱 | 确认 `FEISHU_REPLY_FORMAT=markdown`，飞书需要使用 markdown 格式才能正确渲染 |
| Token 过期 | 执行 `lark-cli auth login --recommend` 重新授权 |
| 偶发断开 | 脚本会自动重启事件消费器；持续失败时查看终端日志中的 `event consumer` 输出 |
| lark-cli 命令不存在 | 确认已安装：`npm install -g @larksuite/cli`，并执行 `npx -y skills add https://open.feishu.cn --skill -y` |

## 相关链接

- [飞书 CLI 安装指南](https://open.feishu.cn/document/no_class/mcp-archive/feishu-cli-installation-guide.md)
- [飞书 CLI 能力指南](https://open.larkoffice.com/document/mcp_open_tools/feishu-cli-let-ai-actually-do-your-work-in-feishu.md)
- [飞书开发者后台](https://open.feishu.cn/app)
- [GitHub 仓库](https://github.com/unsetbad/feishu-agent)
