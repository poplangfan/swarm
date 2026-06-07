<div align="center">
  <h1>Swarm</h1>
  <p><strong>多租户飞书 AI Agent 框架</strong></p>
  <p><em>并发安全 · 轻量级 · 面向企业</em></p>
  <p>
    <img src="https://img.shields.io/badge/python-%E2%89%A53.10-blue" alt="Python">
    <img src="https://img.shields.io/badge/license-MIT-green" alt="License">
    <img src="https://img.shields.io/badge/platform-Feishu-orange" alt="Platform">
    <img src="https://img.shields.io/badge/tests-300%20passed-brightgreen" alt="Tests">
    <img src="https://img.shields.io/badge/code%20style-ruff-blueviolet" alt="Ruff">
  </p>
</div>

---

<p align="center">
  <a href="#swarm-">中文</a> · <a href="#swarm-1">English</a>
</p>

---

<h1 id="swarm-">Swarm <small>中文</small></h1>

**Swarm** 是一个轻量级、并发安全的多租户飞书 AI Agent 框架。提供简洁的 Agent 循环加上生产环境所需组件：WebSocket 长连接、记忆系统、工具系统、用户 OAuth 权限、定时任务和完善的日志系统。

## 借鉴与致谢

Swarm 的项目结构和核心设计参考了两个优秀的 AI Agent 项目：

- **[nanobot](https://github.com/nanobot)** — Agent 循环、工具系统、消息总线的设计灵感
- **[hermes-agent](https://github.com/NousResearch/hermes-agent)** — 扁平化项目结构、插件协议、技能系统

## 为什么选择 Swarm

- **多租户隔离** — 基于 `chat_id` 的完全隔离，存储、运行时、权限三层防护
- **并发安全** — `RequestContext` 显式传递 + 每会话 `asyncio.Lock`，杜绝全局状态竞态
- **WebSocket 原生** — 无需公网 IP、无需内网穿透、无需开放端口
- **用户身份操作** — 飞书 OAuth 原生支持，工具以用户身份执行而非应用身份
- **小核心** — 可读的内部实现，易于理解和自托管
- **企业就绪** — 结构化日志、审计追踪、优雅关闭、Docker 部署

## 快速开始

```bash
git clone https://github.com/poplangfan/swarm.git ~/.swarm
cd ~/.swarm
pip install -e .
swarm init
# 编辑 ~/.swarm/config.yaml 填入凭证
swarm chat
```

安装后 `~/.swarm/` 包含完整源码 + 所有数据：

```
~/.swarm/
├── agent/            # 源代码
├── gateway/          # 源代码
├── tools/            # 源代码
├── cli/              # 源代码
├── ...               # 其他模块
├── config.yaml       # 配置文件
├── sessions.db       # 会话数据
├── chroma/           # 长期记忆
├── logs/             # 日志
└── skills/           # 自定义技能
```

> 也可以从 PyPI 安装：`pip install swarm-agent && swarm init`（不含源码，仅 CLI + 数据目录）

```yaml
# config.yaml
llm:
  provider: "anthropic"
  base_url: "https://api.deepseek.com/anthropic"
  api_key: "${LLM_API_KEY}"
  model: "deepseek-v4-pro"

feishu:
  app_id: "${FEISHU_APP_ID}"
  app_secret: "${FEISHU_APP_SECRET}"
```

## 核心特性

### 架构

- **5 状态 AgentLoop**: RESTORE → BUILD → RUN → SAVE → RESPOND
- **消息总线**: asyncio.Queue 解耦 I/O 和 Agent 逻辑
- **RequestContext**: 不可变请求上下文，杜绝全局可变状态
- **ContextBuilder**: 分层系统提示组装（identity + memory + skills）

### 多租户隔离

```
chat_id=A → asyncio.Lock(A) → ChromaDB:mem_A → SQLite:session_A
chat_id=B → asyncio.Lock(B) → ChromaDB:mem_B → SQLite:session_B
                    ↑ 并发                     ↑ 零交叉污染
```

### 记忆系统

- **短期记忆**: SQLite 按 chat_id 分区存储
- **长期记忆**: ChromaDB 向量存储，按 chat_id 隔离
- **Dream**: 两阶段 LLM 辅助记忆巩固
- **Recall**: 混合召回（向量相似度 + 时间衰减 + 重要性加权）
- **知识图谱**: 跨会话实体和关系提取
- **Compressor**: 轨迹保留的上下文压缩

### 用户授权

```
首次消息 → OAuth 授权链接
用户点击 → 飞书授权
Swarm 用 code 换取 user_access_token
Token 加密存储 (AES-256-GCM) + 自动刷新
后续消息 → 用户身份注入工具调用
```

### 工具系统

- 内置工具：网页搜索、URL 抓取、飞书消息、文件管理、定时任务
- MCP 协议：客户端 + 服务端，与其他 AI Agent 互操作
- Markdown Skills：无代码 Agent 行为定义（10 个内置）
- 插件协议：安装/启用/禁用生命周期
- 权限系统：声明式工具访问控制

### 飞书集成

- WebSocket 长连接（无需 webhook）
- 全消息类型：文本、富文本、图片、音频、文件、贴纸、交互卡片、分享、合并转发
- CardKit 流式输出
- 交互卡片动作处理
- 群管理事件（加入/退出）
- Emoji 状态反馈

### 运维

- 结构化 JSON 日志（structlog）
- 日志轮转 + gzip 压缩
- 审计日志
- 优雅关闭 + 断点保存
- Docker 部署
- systemd/supervisor 服务模板

## 架构图

```
飞书 WS → 消息总线 → AgentLoop(5状态) → 消息总线 → Delivery → 飞书回复
                         │
               ┌─────────┼──────────┐
               ▼         ▼          ▼
           Session    Memory      Tools
           (SQLite)  (ChromaDB)  (Registry)

               Auth (OAuth + 加密Token存储)
```

## 项目结构

```
swarm/
├── agent/         # AgentLoop, Runner, Context, Subagent
├── session/       # Session CRUD, Goal State, Continuation
├── memory/        # ChromaDB, Short-term, Dream, Compressor, KG
├── providers/     # OpenAI, Anthropic, Fallback, Retry
├── gateway/       # Feishu WS, Messages, Reply, Streaming, Events
├── tools/         # Registry, Builtins (web, message, file, cron)
├── auth/          # OAuth, Token Store (AES-256-GCM 加密)
├── events/        # Pub/Sub 事件总线, Metrics, Logging
├── cron/          # APScheduler, SQLite 持久化, NL 解析
├── mcp/           # MCP 客户端 + 服务端
├── plugins/       # 清单协议, 加载器
├── skills/        # Markdown skills 加载器
├── skills_builtin/ # 10 个内置技能
├── delivery/      # 出站队列, 限流, 重试
├── state/         # 持久化状态, 快照, 迁移
├── cli/           # Typer + Rich + prompt_toolkit
├── bus/           # 异步消息总线
├── config/        # Pydantic v2 schema + YAML 加载器
├── docker/        # Dockerfile + Compose
├── tests/         # 315 单元/集成测试
└── logging_/      # structlog + 轮转 + 压缩 + 审计
```

## 文档

- [快速开始](docs/quickstart.md)
- [架构指南](docs/architecture.md)
- [配置说明](docs/configuration.md)
- [飞书设置](docs/feishu-setup.md)
- [认证授权](docs/auth.md)
- [工具开发](docs/tools.md)
- [Skills 开发](docs/skills.md)
- [插件开发](docs/plugins.md)
- [日志监控](docs/logging.md)
- [部署指南](docs/deployment.md)

## 环境要求

- Python 3.10+
- 飞书账号（可创建应用）
- LLM API Key（DeepSeek、OpenAI 或 Anthropic）

## 协议

MIT License — 详见 [LICENSE](LICENSE)

---

<h1 id="swarm-1">Swarm <small>English</small></h1>

**Swarm** is a lightweight, concurrency-safe, multi-tenant Feishu AI Agent framework. It provides a clean agent loop with production-ready components: WebSocket long connection, memory system, tool system, user OAuth permissions, cron scheduler, and comprehensive logging.

## Acknowledgments

Swarm's project structure and core design draw inspiration from two excellent AI agent projects:

- **[nanobot](https://github.com/nanobot)** — Agent loop, tool system, and message bus design
- **[hermes-agent](https://github.com/NousResearch/hermes-agent)** — Flat project structure, plugin protocol, and skill system

## Why Swarm

- **Multi-tenant isolation** — `chat_id`-based isolation at storage, runtime, and auth layers
- **Concurrency-safe** — `RequestContext` explicit passing, per-chat `asyncio.Lock`, no global state races
- **WebSocket native** — No public IP, no ngrok, no open ports needed
- **User-permissioned** — Native Feishu OAuth — tools operate as the requesting user, not as the bot
- **Small core** — Readable internals, easy to understand, extend, and self-host
- **Enterprise-ready** — Structured logging, audit trail, graceful shutdown, Docker deployment

## Quick Start

```bash
git clone https://github.com/poplangfan/swarm.git ~/.swarm
cd ~/.swarm
pip install -e .
swarm init
# Edit ~/.swarm/config.yaml with your credentials
swarm chat
```

After setup, `~/.swarm/` contains both full source code and all data.

> Also available via PyPI: `pip install swarm-agent && swarm init` (CLI-only, no source code)

```yaml
# config.yaml
llm:
  provider: "anthropic"
  base_url: "https://api.deepseek.com/anthropic"
  api_key: "${LLM_API_KEY}"
  model: "deepseek-v4-pro"

feishu:
  app_id: "${FEISHU_APP_ID}"
  app_secret: "${FEISHU_APP_SECRET}"
```

## Core Features

### Architecture

- **5-State AgentLoop**: RESTORE → BUILD → RUN → SAVE → RESPOND
- **Message Bus**: asyncio.Queue decoupling for I/O and agent logic
- **RequestContext**: Immutable per-request isolation — no global mutable state
- **ContextBuilder**: Layered system prompt assembly (identity + memory + skills)

### Multi-Tenant Isolation

```
chat_id=A → asyncio.Lock(A) → ChromaDB:mem_A → SQLite:session_A
chat_id=B → asyncio.Lock(B) → ChromaDB:mem_B → SQLite:session_B
                    ↑ concurrent             ↑ zero cross-contamination
```

### Memory System

- **Short-term**: SQLite per-chat message store
- **Long-term**: ChromaDB vector memory with per-chat collections
- **Dream**: Two-phase LLM-assisted memory consolidation
- **Recall**: Hybrid search (vector similarity + time decay + importance)
- **Knowledge Graph**: Cross-session entity and relationship extraction
- **Compressor**: Trajectory-preserving context window management

### User Authorization

```
First message → OAuth authorization link
User clicks link → authorizes in Feishu
Swarm exchanges code for user_access_token
Token encrypted (AES-256-GCM) + auto-refresh
Subsequent messages → user identity injected into tools
```

### Tools & Skills

- Built-in tools: Web search, URL fetch, Feishu messages, file management, cron
- MCP: Client + server — interoperate with other AI agents
- Markdown Skills: Code-free agent behaviors (10 built-in)
- Plugins: Manifest protocol with install/enable/disable lifecycle
- Permissions: Declarative access control for tools

### Feishu Integration

- WebSocket long connection (no webhook needed)
- All message types: text, post, image, audio, file, sticker, interactive, share, merge_forward
- CardKit streaming output engine
- Interactive card action handling
- Group chat member join/leave events
- Emoji reactions for processing state feedback

### Operations

- Structured JSON logging (structlog)
- Log rotation with gzip compression
- Audit logging for compliance
- Graceful shutdown with checkpoint preservation
- Docker deployment
- systemd/supervisor service templates

## Architecture

```
Feishu WS → MessageBus → AgentLoop(5 states) → MessageBus → Delivery → Feishu Reply
                              │
                    ┌─────────┼──────────┐
                    ▼         ▼          ▼
               Session    Memory      Tools
               (SQLite)  (ChromaDB)  (Registry)

                    Auth (OAuth + Encrypted Token Store)
```

## Project Structure

```
swarm/
├── agent/         # AgentLoop, Runner, Context, Subagent
├── session/       # Session CRUD, Goal State, Continuation
├── memory/        # ChromaDB, Short-term, Dream, Compressor, KG
├── providers/     # OpenAI, Anthropic, Fallback, Retry
├── gateway/       # Feishu WS, Messages, Reply, Streaming, Events
├── tools/         # Registry, Builtins (web, message, file, cron)
├── auth/          # OAuth, Token Store (AES-256-GCM encryption)
├── events/        # Pub/Sub event bus, Metrics, Logging subscribers
├── cron/          # APScheduler, SQLite persistence, NL parsing
├── mcp/           # MCP client + server
├── plugins/       # Manifest protocol, Loader
├── skills/        # Markdown skills loader
├── skills_builtin/ # 10 built-in skills
├── delivery/      # Outbound queuing, rate limiting, retry
├── state/         # Persistent state, snapshots, migration
├── cli/           # Typer + Rich + prompt_toolkit
├── bus/           # Async message bus
├── config/        # Pydantic v2 schema + YAML loader
├── docker/        # Dockerfile + Compose
├── tests/         # 315 unit/integration tests
└── logging_/      # structlog + rotation + compression + audit
```
```

## Documentation

- [Quickstart Guide](docs/quickstart.md)
- [Architecture Guide](docs/architecture.md)
- [Configuration](docs/configuration.md)
- [Feishu Setup](docs/feishu-setup.md)
- [Authentication](docs/auth.md)
- [Tools Guide](docs/tools.md)
- [Skills Guide](docs/skills.md)
- [Plugin Development](docs/plugins.md)
- [Logging & Monitoring](docs/logging.md)
- [Deployment Guide](docs/deployment.md)

## Requirements

- Python 3.10+
- Feishu account with app creation permissions
- LLM API key (DeepSeek, OpenAI, or Anthropic)

## License

MIT License — see [LICENSE](LICENSE)
