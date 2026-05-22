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

## 前置条件

- Python 3.9+
- 已安装并登录 `lark-cli`（`lark-cli auth login`）
- 飞书应用已开启机器人能力
- 飞书开发者后台已启用事件 `im.message.receive_v1`
- 已给应用开通消息接收与消息发送相关权限

## 配置

复制 `.env.example` 为 `.env`，填入你的配置：

```bash
cp .env.example .env
```

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
| `FEISHU_REPLY_MAX_CHARS` | 4000 | 单条回复最大字符数 |
| `FEISHU_REPLY_IN_THREAD` | false | 设为 `true` 时在消息线程里回复 |
| `FEISHU_EVENT_DEDUP_TTL_SECONDS` | 3600 | 事件去重保留时间（秒） |
| `FEISHU_RESTART_DELAY_SECONDS` | 5 | 事件消费器异常退出后的重启间隔（秒） |
| `FEISHU_IGNORE_SENDER_IDS` | 无 | 逗号分隔的 sender open_id，用于忽略指定发送者 |

## 启动

```bash
python3 feishu_agent.py
```

启动后日志会显示当前使用的 API 类型和模型名。在飞书里私聊机器人，或在群里 @机器人，即可触发回复。

## 后台运行

推荐使用 `tmux` 或 `screen` 保持进程：

```bash
tmux new -s feishu-agent
python3 feishu_agent.py
# Ctrl+B D 脱离，tmux attach -t feishu-agent 重新连接
```

## 消息处理流程

1. 只处理 `text` 类型消息（图片、文件等自动忽略）
2. 消息经过去重（同一 event_id 在 TTL 内不重复处理）
3. 可通过 `FEISHU_IGNORE_SENDER_IDS` 屏蔽特定用户
4. 支持自动重连：事件消费器异常退出后会自动重启

## 常见问题

- **收不到消息**：确认机器人已被添加到群聊，或应用已发布/可用
- **权限不足**：在飞书开发者后台开通缺失 scope，重新执行 `lark-cli auth login`
- **模型报错**：检查 `LLM_BASE_URL`、`LLM_API_KEY`、`LLM_MODEL` 是否匹配你的服务
- **偶发断开**：脚本会自动重启事件消费器；持续失败时查看终端日志
- **Anthropic 接口 404**：确认 `LLM_BASE_URL` 路径正确（如小米 MiMo 用 `/anthropic` 结尾）
