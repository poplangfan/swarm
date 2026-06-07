# Swarm Framework Design Spec

**Date**: 2026-06-06  
**Status**: Approved  
**Target scale**: ~55,000–60,000 lines (core + tests + docs)

## 1. Overview

Swarm is a lightweight, concurrency-safe, multi-tenant Feishu AI Agent framework built from scratch. It draws design inspiration from nanobot and hermes-agent but contains zero copied code — every line is independently implemented.

### 1.1 Design Goals

| Goal | Description |
|------|-------------|
| Feishu-only | No other platform support. Deep feishu protocol integration. |
| Multi-tenant isolation | `chat_id`-based isolation at storage, runtime, and auth layers. |
| Concurrency-safe | Explicit `RequestContext` passing, per-chat `asyncio.Lock`, no global mutable state. |
| CLI + WebSocket | Same AgentLoop serves both `swarm chat` interactive CLI and `swarm ws` production mode. |
| User-permissioned | Native Feishu OAuth: tools operate as the requesting user, not as the bot app. |
| Observable | Structured JSON logging, trace_id throughout, audit log, metrics events. |
| Extensible | Plugin protocol, Markdown Skills, MCP client + server. |

### 1.2 Reference Sources

| Source | Lines | Absorbed Designs |
|--------|:-----:|------------------|
| nanobot | ~142,000 | AgentLoop state machine, RequestContext immutability, MessageBus, Dream memory consolidation, Skills system, Provider factory, RuntimeEventBus, Cron, Subagent, Session manager, Goal state, Turn continuation |
| hermes-agent | ~292,000 | Gateway lifecycle, Trajectory compression, Streaming event types, Delivery layer, Token management, Graceful shutdown, Signal handling, Plugin protocol, State persistence |
| Original | — | Feishu OAuth user-permission model, Encrypted token storage, CardKit streaming engine, Full feishu message type parser, Group chat identity-based operations, Knowledge graph memory layer, Audit logging |

## 2. Architecture

### 2.1 System Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Feishu Open Platform                          │
└────────────────────────────┬────────────────────────────────────────┘
                             │ WebSocket (long connection)
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                       Gateway Layer                                   │
│  ┌───────────────┐  ┌───────────────┐  ┌────────────────────────┐   │
│  │ feishu_ws.py  │  │  delivery.py  │  │  feishu_streaming.py   │   │
│  │ WS lifecycle  │  │  Queue/retry  │  │  CardKit engine         │   │
│  └───────┬───────┘  └───────┬───────┘  └────────────────────────┘   │
└──────────┼──────────────────┼───────────────────────────────────────┘
           │                  │
           ▼                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        Message Bus                                    │
│              asyncio.Queue — decouples I/O from agent                 │
└────────────────────────────┬────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                       Agent Layer                                     │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │           AgentLoop State Machine (5 states)                   │   │
│  │  RESTORE → BUILD → RUN → SAVE → RESPOND → DONE                │   │
│  └──────────────────────────┬───────────────────────────────────┘   │
│                             │                                        │
│  ┌──────────────┐  ┌────────┴───────┐  ┌──────────────────────┐     │
│  │ context.py   │  │  runner.py     │  │  subagent.py          │     │
│  │ RequestCtx   │  │  LLM + Tool    │  │  Spawn/pool/monitor   │     │
│  │ (frozen)     │  │  execution loop│  │                       │     │
│  └──────────────┘  └────────────────┘  └──────────────────────┘     │
└─────────────────────────────────────────────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      Storage Layer                                    │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐               │
│  │ memory/      │  │ session/     │  │ auth/        │               │
│  │ ChromaDB     │  │ SQLite       │  │ SQLite+encr  │               │
│  │ + Dream      │  │ + Manager    │  │ Token store  │               │
│  └──────────────┘  └──────────────┘  └──────────────┘               │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.2 RequestContext — Concurrency Safety Core

```python
from dataclasses import dataclass
from typing import FrozenSet

@dataclass(frozen=True)
class RequestContext:
    """Immutable per-request context. Passed explicitly to ALL stateful functions."""

    trace_id: str                # UUID — traces request through all subsystems
    chat_id: str                 # Tenant key — the root of all isolation
    chat_type: str               # "p2p" | "group"
    user_id: str                 # Feishu open_id of the message sender
    message_id: str              # Feishu message_id for idempotency
    user_token: str | None       # user_access_token (None if not yet authorized)
    permissions: FrozenSet[str]  # Granted permissions
    metadata: FrozenSet[tuple]   # Immutable extra data (channel, locale, etc.)
```

**Hard rule**: Any function that needs session state MUST accept `ctx: RequestContext` as its first parameter. Framework-level code MUST NOT use `os.environ` or `contextvars` to store per-request data.

### 2.3 AgentLoop State Machine

```
                    ┌─────────────────────────────────────┐
                    │                                     │
                    ▼                                     │
              ┌──────────┐                                │
              │ RESTORE  │  load session, restore ckpt    │
              └────┬─────┘                                │
                   │ ok                                   │
                   ▼                                      │
              ┌──────────┐                                │
              │  BUILD   │  assemble context              │
              └────┬─────┘  (system prompt + memory       │
                   │         + skills + history           │
                   │         + user_token)                │
          ┌────────┼────────┐                             │
          │ ok     │ command │                             │
          ▼        ▼        │                             │
    ┌──────────┐  ┌──────────────────┐                    │
    │   RUN    │  │ command dispatch │                    │
    │ LLM call │  │ (skip LLM)       │                    │
    │ +tool    │  └────────┬─────────┘                    │
    │ loop     │           │                              │
    └────┬─────┘           │                              │
         │                 │                              │
         │ ok              │                              │
         ▼                 │                              │
    ┌──────────┐           │                              │
    │   SAVE   │           │                              │
    │ persist  │           │                              │
    │ session  │           │                              │
    └────┬─────┘           │                              │
         │                 │                              │
         ▼                 │                              │
    ┌──────────┐           │                              │
    │ RESPOND  │◄──────────┘                              │
    │ send msg │                                          │
    └────┬─────┘                                          │
         │                                                │
         ▼                                                │
    ┌──────────┐                                          │
    │   DONE   │──────────────────────────────────────────┘
    └──────────┘     (turn complete, return to event loop)
```

**5 states** (vs nanobot's 7): COMPACT merged into BUILD, COMMAND handled as BUILD hook intercept.

State transitions are defined as a dict:

```python
_TRANSITIONS: dict[tuple[TurnState, str], TurnState] = {
    (TurnState.RESTORE, "ok"):     TurnState.BUILD,
    (TurnState.BUILD,   "ok"):     TurnState.RUN,
    (TurnState.BUILD,   "cmd"):    TurnState.RESPOND,  # command shortcut
    (TurnState.RUN,     "ok"):     TurnState.SAVE,
    (TurnState.SAVE,    "ok"):     TurnState.RESPOND,
    (TurnState.RESPOND, "ok"):     TurnState.DONE,
}
```

### 2.4 Message Flow

```
Inbound:
  Feishu WS on_message
    → Event type filter (im.message.receive_v1)
    → Message dedup (message_id → bloom filter + SQLite)
    → Content extraction:
        text:        direct
        post:        extract text + image_keys
        image:       download → local media dir
        audio:       download → transcription (optional)
        file:        download → local media dir
        share_chat:  extract description
        interactive: extract card text
        sticker:     "[sticker]"
        system:      ignore
    → InboundMessage(channel, chat_id, content, media, metadata)
    → bus.publish_inbound()

Outbound (streaming):
  Agent starts response
    → feishu_reply.create_card("🐝 thinking...")
    → Each LLM delta → CardKit streaming API update
    → Final content → CardKit finalize
    → Optionally: add reaction emoji (✅ done / ❌ error)

Outbound (non-streaming):
  Agent complete → Delivery.send → feishu_reply.send()
```

### 2.5 Concurrency Model

```
Message Bus
    │
    ├── msg for chat_id=A ──► asyncio.Lock("A") ──► AgentLoop._dispatch(msg_A)
    │                                                      │
    ├── msg for chat_id=B ──► asyncio.Lock("B") ──► AgentLoop._dispatch(msg_B)
    │                                                      │ (concurrent with A)
    └── msg for chat_id=A ──► pending_queue["A"] ──────────┘ (injected mid-turn)
```

- Each `chat_id` has its own `asyncio.Lock` — same-chat messages are serialized.
- Different chat_ids process concurrently.
- A message arriving while a turn is in flight for the same chat_id is queued for mid-turn injection (if appropriate) or re-published after the turn completes.
- Global concurrency limit via `asyncio.Semaphore` (default: 10 concurrent turns).

## 3. Module Design

### 3.1 Directory Structure

```
swarm/
├── __init__.py                   # Version, logo string
├── __main__.py                   # python -m swarm entry
├── pyproject.toml                # Build config (hatch/uv)
├── config.yaml.example           # Annotated example config
│
├── agent/            ~3,500 lines
│   ├── __init__.py
│   ├── loop.py                   # AgentLoop state machine + dispatch
│   ├── context.py                # RequestContext, ContextBuilder
│   ├── runner.py                 # AgentRunner: LLM call + tool execution loop
│   └── subagent.py               # Subagent spawn, pool, lifecycle
│
├── session/          ~1,500 lines
│   ├── __init__.py
│   ├── manager.py                # Session CRUD, TTL, per-chat_id index
│   ├── goal_state.py             # Sustained goal tracking across turns
│   └── continuation.py           # Turn continuation for truncated responses
│
├── state/            ~800 lines
│   ├── __init__.py
│   ├── store.py                  # Persistent state across restarts
│   ├── snapshot.py               # State snapshot/restore
│   └── migration.py              # Schema/data migration between versions
│
├── providers/        ~2,500 lines
│   ├── __init__.py
│   ├── base.py                   # Abstract provider: chat(), stream(), count_tokens()
│   ├── openai_compat.py          # OpenAI-compatible (vLLM, Ollama, etc.)
│   ├── anthropic.py              # Anthropic native (better tool use semantics)
│   ├── factory.py                # Provider instantiation from config
│   ├── fallback.py               # Fallback chain on failure
│   ├── retry.py                  # Exponential backoff + jitter
│   └── token_counter.py          # tiktoken exact count + estimation fallback
│
├── gateway/          ~3,000 lines
│   ├── __init__.py
│   ├── feishu_ws.py              # WebSocket lifecycle (connect/reconnect/heartbeat)
│   ├── feishu_events.py          # Event dispatch (all event types)
│   ├── feishu_message.py         # Inbound message parser (all msg_types)
│   ├── feishu_reply.py           # Outbound message builder (text/post/card)
│   ├── feishu_streaming.py       # CardKit streaming engine
│   ├── feishu_media.py           # Image/file/audio download and upload
│   └── feishu_actions.py         # Card interactive action callbacks
│
├── delivery/         ~800 lines
│   ├── __init__.py
│   └── delivery.py               # Queue, rate-limit, retry, delivery confirmation
│
├── memory/           ~3,000 lines
│   ├── __init__.py
│   ├── store.py                  # ChromaDB wrapper (collections, metadata filtering)
│   ├── short_term.py             # SQLite short-term message store (partitioned by chat_id)
│   ├── dream.py                  # Two-phase memory consolidation
│   ├── compressor.py             # Context compression (hermes trajectory approach)
│   ├── recall.py                 # Hybrid recall: vector + time-decay + importance
│   └── knowledge_graph.py        # Cross-session entity/relation extraction
│
├── tools/            ~3,000 lines
│   ├── __init__.py
│   ├── registry.py               # Tool registration + lookup + permission check
│   ├── base.py                   # Tool base class + tool_result formatting
│   ├── discovery.py              # pkgutil auto-scan + setuptools entry-point
│   ├── schema.py                 # JSON Schema generation for LLM tool definitions
│   ├── permission.py             # Tool permission declaration + runtime enforcement
│   ├── loader.py                 # External plugin loader via entry_point
│   └── builtin/
│       ├── __init__.py
│       ├── message.py            # Feishu message operations (send, reply, react)
│       ├── web_search.py         # Web search (DuckDuckGo + Bing API)
│       ├── web_fetch.py          # URL content fetch → Markdown
│       ├── cron.py               # Cron task create/list/delete
│       ├── file.py               # Feishu file operations
│       └── system.py             # /help, /status, /clear commands
│
├── auth/             ~1,500 lines
│   ├── __init__.py
│   ├── oauth.py                  # Feishu OAuth flow (authorize → code → token)
│   ├── token_store.py            # AES-encrypted SQLite token storage + auto-refresh
│   ├── middleware.py              # Request-level token injection
│   └── callback_server.py        # OAuth redirect HTTP server (local)
│
├── cron/             ~1,200 lines
│   ├── __init__.py
│   ├── scheduler.py              # APScheduler wrapper
│   ├── store.py                  # SQLite persistence (survives restart)
│   ├── parser.py                 # Natural language → cron expression (LLM-assisted)
│   └── jobs/
│       ├── __init__.py
│       ├── heartbeat.py          # Health check
│       ├── memory_consolidation.py  # Periodic Dream trigger
│       └── soul_evolution.py     # Periodic persona update
│
├── events/           ~800 lines
│   ├── __init__.py
│   ├── bus.py                    # Publish/subscribe event bus
│   ├── types.py                  # Event type definitions
│   └── subscribers/
│       ├── __init__.py
│       ├── logging.py            # All events → structured log
│       ├── metrics.py            # Latency/throughput/error metrics
│       └── health.py             # Health status notifications
│
├── mcp/              ~1,000 lines
│   ├── __init__.py
│   ├── client.py                 # MCP client (connect to external MCP servers)
│   ├── manager.py                # Multi-server lifecycle management
│   ├── tool_bridge.py            # MCP tool → Swarm tool registry bridge
│   └── server.py                 # Swarm as MCP server (expose tools to other agents)
│
├── plugins/          ~800 lines
│   ├── __init__.py
│   ├── protocol.py               # Plugin manifest protocol
│   ├── loader.py                 # Plugin discovery + lifecycle
│   └── registry.py               # Plugin registry
│
├── skills/           ~1,200 lines
│   ├── __init__.py
│   └── loader.py                 # Markdown Skills loader (frontmatter + content)
│
├── cli/              ~1,500 lines
│   ├── __init__.py
│   ├── main.py                   # Typer CLI entry (swarm chat / swarm ws / swarm init)
│   ├── chat.py                   # Rich + prompt_toolkit interactive REPL
│   └── stream.py                 # Terminal streaming renderer
│
├── bus/              ~200 lines
│   ├── __init__.py
│   └── queue.py                  # Async message bus (asyncio.Queue)
│
├── config/           ~1,000 lines
│   ├── __init__.py
│   ├── schema.py                 # Pydantic v2 config schema with validators
│   ├── loader.py                 # YAML + ${ENV_VAR} substitution + default merge
│   └── paths.py                  # XDG-compatible path resolution
│
├── logging_/         ~1,000 lines
│   ├── __init__.py
│   ├── setup.py                  # structlog configuration
│   ├── handlers.py               # TimedRotatingFile + gzip compression
│   ├── audit.py                  # Audit log (compliance: who did what when)
│   ├── trace.py                  # trace_id injection throughout call chain
│   ├── query.py                  # Log query by time/chat_id/user_id/level
│   ├── export.py                 # Export logs (JSON/CSV)
│   └── metrics.py                # Key metric collection
│
├── utils/            ~800 lines
│   ├── __init__.py
│   ├── helpers.py                # Common utilities
│   ├── template.py               # Jinja2 template rendering
│   ├── media.py                  # Image/audio format helpers
│   └── text.py                   # Text truncation, markdown helpers
│
├── skills_builtin/   ~3,000 lines
│   │                            # Bundled Markdown Skills:
│   ├── base-assistant/SKILL.md   # Default assistant persona
│   ├── feishu-docs/SKILL.md      # Feishu document operations (placeholder)
│   ├── calendar/SKILL.md         # Calendar management
│   ├── summary/SKILL.md          # Conversation summarization
│   ├── translator/SKILL.md       # Multi-language translation
│   ├── code-review/SKILL.md      # Code review assistant
│   ├── data-analysis/SKILL.md   # Data analysis helper
│   ├── meeting-notes/SKILL.md    # Meeting notes generator
│   ├── reminder/SKILL.md         # Reminder/task tracking
│   └── customer-support/SKILL.md # Customer support assistant
│
├── tests/            ~12,000 lines
│   ├── conftest.py
│   ├── test_agent_loop.py
│   ├── test_context_isolation.py
│   ├── test_runner.py
│   ├── test_subagent.py
│   ├── test_session.py
│   ├── test_state.py
│   ├── test_providers.py
│   ├── test_feishu_ws.py
│   ├── test_feishu_message.py
│   ├── test_delivery.py
│   ├── test_memory.py
│   ├── test_tools.py
│   ├── test_auth.py
│   ├── test_cron.py
│   ├── test_events.py
│   ├── test_mcp.py
│   ├── test_plugins.py
│   ├── test_skills.py
│   ├── test_cli.py
│   ├── test_config.py
│   └── test_logging.py
│
├── docs/             ~4,000 lines
│   ├── index.md                  # Documentation home
│   ├── quickstart.md             # 5-minute quickstart
│   ├── installation.md           # Detailed install guide
│   ├── architecture.md           # Architecture deep-dive
│   ├── configuration.md          # All config options
│   ├── feishu-setup.md           # Feishu app setup guide
│   ├── auth.md                   # User OAuth flow
│   ├── skills.md                 # Writing custom Skills
│   ├── tools.md                  # Tool development guide
│   ├── plugins.md                # Plugin development
│   ├── deployment.md             # Production deployment
│   ├── logging.md                # Logging & monitoring
│   ├── api/                      # API reference (auto-generated)
│   └── changelog.md
│
├── examples/         ~1,500 lines
│   ├── basic-bot/                # Minimal feishu bot
│   ├── custom-tool/              # Custom tool example
│   ├── custom-skill/             # Custom Skill example
│   └── multi-tenant/             # Multi-tenant setup
│
├── docker/           ~500 lines
│   ├── Dockerfile
│   ├── docker-compose.yml
│   └── entrypoint.sh
│
├── scripts/          ~500 lines
│   ├── release.sh
│   └── gen_api_docs.py
│
├── .github/
│   └── workflows/
│       ├── ci.yml                # pytest + ruff + coverage
│       ├── release.yml           # PyPI publish
│       └── docs.yml              # Docs build + deploy
│
├── README.md                     # English
├── README_ZH.md                  # Chinese
├── LICENSE                       # MIT
├── CHANGELOG.md
├── CODE_OF_CONDUCT.md
├── CONTRIBUTING.md
├── SECURITY.md
└── .gitignore
```

### 3.2 Core Module Details

#### agent/loop.py — AgentLoop

The central orchestrator. Key responsibilities:

- Consume `InboundMessage` from the bus
- For each message: RESTORE → BUILD → RUN → SAVE → RESPOND
- Manage per-session locks and concurrency gate
- Route pending messages for active sessions to injection queues
- Handle `/stop` (cancel active task, preserve checkpoint)
- Handle graceful shutdown (drain active turns → save all sessions → close DBs)

#### agent/runner.py — AgentRunner

Executes one complete LLM turn:

```
while iteration < max_iterations:
    response = await provider.chat(messages, tools, stream=True)
    if response.has_tool_calls():
        for tool_call in response.tool_calls:
            result = await execute_tool(tool_call, ctx)
            messages.append(tool_result(result))
        continue  # another LLM round
    else:
        return response.content  # final answer
```

Supports:
- Streaming output (deltas forwarded to `on_stream` callback)
- Tool call execution with timeout (per-tool `asyncio.wait_for`)
- Mid-turn message injection (from pending_queue)
- Checkpoint callbacks (persist partial state before each tool execution)
- Reasoning/thinking block extraction (for DeepSeek-R1, Claude thinking)

#### agent/context.py — ContextBuilder

Assembles the system prompt and message list for each LLM call:

```
System Prompt =
    Identity (workspace, runtime info)
    + Bootstrap files (AGENTS.md, SOUL.md, USER.md)
    + Tool contract (usage rules)
    + Memory context (ChromaDB recall)
    + Always-active Skills
    + Available Skills summary
    + Recent history summary
    + Session summary (compressed archive)

User Message =
    Message content
    + Media attachments (images as base64 data URIs)
    + Runtime context block (time, channel, chat_id, sender, token status)
```

#### agent/subagent.py — Subagent System

```
Main AgentLoop identifies complex task
  → create SubagentContext(
        parent_trace_id,
        task_description,
        inherited_token=ctx.user_token,
        max_iterations=15,
        timeout=300s
    )
  → spawn asyncio.Task for each subagent
  → results injected into main session via pending_queue
  → subagent session marked ephemeral (ChromaDB cleaned after merge)
```

Constraints:
- Max 3 concurrent subagents per main session
- Subagents cannot recursively spawn
- Subagent tools restricted (no auth ops, no cron modification)

### 3.3 Memory System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      Memory Pipeline                         │
│                                                              │
│  Message Received                                             │
│      │                                                       │
│      ▼                                                       │
│  ┌──────────────┐                                            │
│  │ Short-term    │  SQLite: messages table                    │
│  │ Memory        │  Partitioned by chat_id                    │
│  └──────┬───────┘  TTL: 7 days (configurable)                │
│         │                                                     │
│         │ threshold reached (20 messages)                     │
│         ▼                                                     │
│  ┌──────────────┐                                            │
│  │ Dream Phase 1 │  LLM extracts key facts from recent msgs   │
│  │ (Extraction)  │  Output: structured fact list               │
│  └──────┬───────┘                                            │
│         │                                                     │
│         ▼                                                     │
│  ┌──────────────┐                                            │
│  │ Dream Phase 2 │  Facts → embeddings → ChromaDB             │
│  │ (Storage)     │  Collection: "memory:{chat_id}"            │
│  └──────┬───────┘  Metadata: {user_id, timestamp, importance} │
│         │                                                     │
│         ▼                                                     │
│  ┌──────────────┐                                            │
│  │ Knowledge     │  Cross-session entity extraction           │
│  │ Graph         │  Relations: "user_x works_on project_y"    │
│  └──────────────┘  Storage: SQLite graph tables               │
│                                                              │
│  Recall (query time):                                         │
│    Hybrid = ChromaDB.similarity(query, k=10)                 │
│           + time_decay_weight(recency)                        │
│           + importance_weight(source reliability)             │
│           + graph_hop(entity expansion)                       │
│    → Top-K facts injected into system prompt                  │
└─────────────────────────────────────────────────────────────┘
```

**Isolation guarantee**: ChromaDB collections are named `memory:{chat_id}`. Private chats and group chats have separate collections. Cross-contamination is impossible at the storage level.

### 3.4 User Authorization Flow

```
First message from user
  → token_store.lookup(user_id) → None
  → Agent responds with OAuth authorization URL
    "请点击链接授权：https://open.feishu.cn/...&redirect_uri=..."
  → User clicks link, authorizes in Feishu
  → Feishu redirects to Swarm's callback server
  → Swarm exchanges code for user_access_token + refresh_token
  → token_store.save(user_id, encrypted_token_data)
  → Notify user: "授权成功！请重新发送您的消息。"
  → (User resends message)

Subsequent messages
  → token_store.lookup(user_id) → TokenData
  → If access_token expired:
      token_store.refresh(user_id)  # uses refresh_token
  → ctx = RequestContext(user_token=valid_access_token, ...)
  → Tools use ctx.user_token to call Feishu APIs on user's behalf

Group chat
  → Message sender's identity is used
  → ctx.user_token = token_store.lookup(sender_user_id)
  → If sender hasn't authorized → tool operates with app-level token only
  → If sender has authorized → tool operates with user's token
```

Token storage: SQLite table encrypted with AES-256-GCM (`cryptography` library). Encryption key injected via environment variable `TOKEN_ENCRYPT_KEY` or config file.

**Note on redirect_uri**: Because the OAuth redirect happens in the user's browser (not server-to-server), `localhost` or LAN IP addresses work fine — the user's browser simply needs to reach the callback server. Swarm starts a lightweight HTTP server on the configured port to receive the OAuth code. No public IP or HTTPS is required, consistent with the WebSocket-only architecture (no inbound webhooks from Feishu).

### 3.5 Provider Layer

```
Provider Factory
  config.llm.provider = "openai"    → OpenAICompatProvider
  config.llm.provider = "anthropic" → AnthropicProvider
  config.llm.provider = "custom"    → OpenAICompatProvider(base_url=custom_url)

Fallback Chain:
  primary: gpt-4o
    ↓ (network error / rate limit)
  secondary: claude-sonnet-4-6
    ↓ (provider down)
  tertiary: local-llama (ollama)

Token Budget:
  context_window = provider.context_window (or configured)
  reserved_output = provider.max_tokens or 4096
  available_input = context_window - reserved_output - 1024 (buffer)
  → Session history is trimmed to fit within available_input
```

### 3.6 Delivery Layer

Independent queue-per-chat_id for outbound message ordering:

```
OutboundMessage
  → Delivery.send(msg)
    → chat_id-level queue (FIFO, preserves order)
    → Global rate limiter (10 req/s for Feishu API)
    → Send via feishu_reply
    → On failure: retry up to 3 times, exponential backoff
    → On permanent failure: log error, notify via events bus
    → Record delivery status in delivery_log table
```

### 3.7 Plugin Protocol

```
Plugin Manifest:
  schema: "swarm-plugin.v1"
  name: "feishu-docs"
  version: "0.1.0"
  capabilities:
    - type: "tool"
      provides: ["feishu_doc_read", "feishu_doc_write"]
  install:
    pip: ["feishu-docs-plugin>=0.1.0"]
  permissions:
    - "drive:drive:read"
    - "docx:document:readwrite"

Plugin Lifecycle:
  discover (entry_point "swarm.plugins")
  → validate (manifest schema check)
  → install (pip install dependencies)
  → load (import module, register tools/skills)
  → enable (start any background tasks)
  → disable (stop tasks, but keep registered)
  → unload
```

### 3.8 Feishu Event Handling

All handled event types:

| Event | Handler | Action |
|-------|---------|--------|
| `im.message.receive_v1` | Core | Parse content → InboundMessage |
| `im.message.reaction.created` | Optional | Track user feedback |
| `im.chat.member.user.added` | Lifecycle | Welcome message, init session |
| `im.chat.member.user.deleted` | Lifecycle | Mark session inactive |
| `im.chat.disbanded` | Lifecycle | Archive session, cleanup |
| `card.action.trigger` | Interaction | Handle interactive card button clicks |
| `app_ticket` | Platform | Verify event authenticity |

Event verification: Feishu pushes `app_ticket` periodically (used to verify event signatures via SHA256). Swarm caches the ticket in memory and uses it to validate all incoming event signatures, preventing spoofed messages.

`feishu_actions.py` handles interactive card callbacks — when users click buttons or submit forms in Swarm's message cards, the action payload is routed back into the AgentLoop as a synthetic message, enabling multi-step interactive workflows.

## 4. Configuration

### 4.1 Config Schema (Pydantic v2)

```yaml
# swarm/config.yaml
llm:
  provider: "openai"              # openai | anthropic | custom
  base_url: "https://api.openai.com/v1"
  api_key: "${LLM_API_KEY}"
  model: "gpt-4o"
  max_tokens: 4096
  temperature: 0.7
  fallback:                       # Optional fallback chain
    - provider: "anthropic"
      api_key: "${ANTHROPIC_API_KEY}"
      model: "claude-sonnet-4-6"

feishu:
  app_id: "${FEISHU_APP_ID}"
  app_secret: "${FEISHU_APP_SECRET}"
  domain: "feishu"                # feishu | lark
  streaming: true
  stream_edit_interval: 0.5       # seconds between CardKit updates
  group_policy: "mention"         # mention | open
  topic_isolation: true           # separate session per group thread/topic
  reply_to_message: false         # quote original message in reply

auth:
  enabled: true
  redirect_uri: "http://localhost:9876/oauth/callback"
  token_encrypt_key: "${TOKEN_ENCRYPT_KEY}"
  scopes:
    - "im:message"
    - "drive:drive:read"
    - "docx:document:read"

memory:
  chroma_path: "./data/chroma"
  short_term_ttl_days: 7
  consolidation_threshold: 20     # messages before Dream triggers
  max_context_tokens: 32000
  dream_model: "gpt-4o-mini"      # cheaper model for extraction

cron:
  jobs:
    memory_consolidation:
      interval_minutes: 30
    soul_evolution:
      interval_minutes: 240

logging:
  level: "INFO"
  json_format: true
  log_dir: "./data/logs"
  retention_days: 30
  compress: true
  audit_enabled: true
  error_separate: true

tools:
  web_search:
    enabled: true
    provider: "duckduckgo"
  subagent:
    max_concurrent: 3
    timeout_seconds: 300
  sandbox:
    enabled: false                 # Code execution (off by default)
```

`${ENV_VAR}` syntax resolves from environment at startup. Missing required env vars cause startup failure with a clear error message.

## 5. Error Handling Strategy

### 5.1 Layered Error Handling

```
Layer 1 — LLM (AgentRunner):
  - Network error     → retry 3x, exponential backoff (1s, 2s, 4s)
  - 429 rate limit    → wait Retry-After header, then retry
  - 5xx server error  → retry 3x, then fallback to next provider
  - Timeout           → return partial content if any
  - All LLM errors    → log with trace_id, notify events bus

Layer 2 — Tool execution:
  - Tool exception    → catch, return tool_result(error=msg)
  - Tool timeout      → asyncio.wait_for, inject timeout error result
  - Tool errors never crash the AgentLoop

Layer 3 — Session/Memory:
  - Save failure      → degrade to in-memory, WARNING log
  - ChromaDB failure  → mark session, attempt repair on next RESTORE
  - Checkpoint restore→ return clean initial state on failure

Layer 4 — Feishu WebSocket:
  - WS disconnect     → auto-reconnect, exponential backoff (1s→2s→...→60s max)
  - Send failure      → Delivery retry queue
  - Token expired     → auto-refresh, on failure notify user to re-auth

Layer 5 — Global:
  - Unhandled exception → logging.critical + process continues
  - SIGTERM/SIGINT      → graceful shutdown:
      1. Stop accepting new messages
      2. Complete in-flight turns (with timeout)
      3. Save all sessions
      4. Close DB connections
      5. Exit
```

### 5.2 Graceful Shutdown Sequence

```
SIGTERM/SIGINT received
  → set shutdown_flag
  → bus.stop_accepting()           # reject new inbound messages
  → await asyncio.wait_for(
        drain_active_turns(),      # let current turns finish
        timeout=30.0
    )
  → cancel_remaining_turns()       # force-cancel, preserve checkpoints
  → save_all_sessions()
  → close_chromadb()
  → close_sqlite()
  → close_feishu_ws()
  → sys.exit(0)
```

## 6. Testing Strategy

### 6.1 Coverage Targets

| Test Type | Target | Focus |
|-----------|:------:|-------|
| Unit tests | 70% of core | Each module independent, mock external deps |
| Integration tests | 20% of core | Multi-module chains, mock LLM/Feishu |
| Concurrency tests | 10% of core | Isolation verification, race conditions |

### 6.2 Critical Test Cases

**Concurrency Safety (highest priority)**:
```
Test: 10 different chat_ids send messages simultaneously
  → Verify each ChromaDB write has correct chat_id metadata
  → Verify zero cross-contamination in recall

Test: Same chat_id receives 5 messages concurrently
  → Verify all 5 are processed serially (no interleaving)
  → Verify session state is consistent after all complete

Test: Token refresh race
  → Two concurrent requests trigger refresh for same user
  → Verify only one refresh actually executes
  → Verify both requests get the new token
```

**Agent Loop**:
```
Test: Happy path (simple text → assistant response)
Test: Tool call loop (search → result → final answer)
Test: Command shortcut (/help skips LLM)
Test: Subagent spawn and result injection
Test: Turn continuation (long response truncated → auto-continue)
Test: /stop mid-turn (checkpoint preserved)
Test: Crash recovery (checkpoint restored on next message)
Test: Message dedup (same message_id → ignored)
```

**Auth**:
```
Test: Unauthorized user → OAuth URL response
Test: Authorized user → token injected into ctx
Test: Expired token → auto-refresh succeeds
Test: Expired refresh_token → re-auth prompt
Test: Token encryption/decryption roundtrip
```

### 6.3 Test Infrastructure

- `pytest` + `pytest-asyncio` (auto mode)
- `pytest-cov` with 80% minimum coverage
- `conftest.py` fixtures: `mock_llm`, `temp_chroma_db`, `sample_ctx`, `mock_feishu_ws`
- ChromaDB in ephemeral mode for tests
- SQLite in `:memory:` for tests

## 7. Logging & Observability

### 7.1 Log Format

```json
{
  "timestamp": "2026-06-06T14:23:45.123Z",
  "level": "INFO",
  "event": "turn_completed",
  "trace_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "chat_id": "oc_xxx",
  "user_id": "ou_yyy",
  "chat_type": "p2p",
  "latency_ms": 1234,
  "tools_used": ["web_search", "feishu_send_message"],
  "stop_reason": "end_turn",
  "logger": "swarm.agent.loop"
}
```

### 7.2 Log Strategy

- **Application logs**: structlog JSON → daily rotation → 30-day retention → gzip compression
- **Audit logs**: Separate file, records all user-identifiable actions (who queried what, which tools used)
- **Error logs**: `ERROR` and above separated into `errors-YYYY-MM-DD.log`
- **Remote push**: `ERROR` and `FATAL` events can be pushed to a Feishu admin group via webhook (configurable)

### 7.3 Metrics Events

| Metric | Description |
|--------|-------------|
| `turn_latency_ms` | Wall clock time from message receipt to response sent |
| `llm_latency_ms` | Time spent waiting for LLM API |
| `tool_latency_ms` | Per-tool execution time |
| `tokens_used` | Input + output tokens per turn |
| `active_sessions` | Current number of active sessions |
| `ws_connected` | WebSocket connection state (0/1) |
| `error_rate` | Errors per minute |

## 8. Runtime Events

```
Event Types:
  session_created       → new chat_id session initialized
  session_expired       → session TTL exceeded
  turn_started          → inbound message processing begins
  turn_completed        → response sent successfully
  tool_executed         → tool called with result
  subagent_spawned      → subagent created
  subagent_completed    → subagent result received
  token_refreshed       → user token renewed
  memory_consolidated   → Dream cycle completed
  error_occurred        → any error at any layer
  health_changed        → component health status change
```

Subscribers: logging handler, metrics collector, health monitor, admin webhook notifier.

## 9. CLI Design

### 9.1 Commands

```bash
swarm init              # Interactive config wizard
swarm chat              # Interactive REPL (Rich + prompt_toolkit)
swarm chat --session X  # Use specific session
swarm chat --ephemeral  # No session persistence
swarm ws                # Start Feishu WebSocket mode
swarm ws --config X     # Custom config path
swarm version           # Print version
swarm validate          # Validate config file
```

### 9.2 Interactive Chat Features

- Rich Markdown rendering (syntax highlighting, tables)
- prompt_toolkit history (↑/↓, Ctrl-R search)
- Multi-line paste support
- Streaming response display ("🐝 is thinking..." spinner → live text)
- Commands: `/help` `/clear` `/soul` `/memory` `/status` `/export` `/exit`
- History persisted to `~/.swarm/chat_history`

## 10. Project Scale Summary

| Category | Lines | Percentage |
|----------|:-----:|:----------:|
| Core Framework | ~26,300 | 44% |
| Tests | ~12,000 | 20% |
| Built-in Skills | ~3,000 | 5% |
| Documentation | ~4,000 | 7% |
| Examples | ~1,500 | 3% |
| Docker/Scripts | ~1,000 | 2% |
| Error handling + Docstrings | ~6,000 | 10% |
| Reserved (plugin interfaces) | ~6,000 | 10% |
| **Total** | **~59,800** | **100%** |

## 11. Open Source Readiness Checklist

- [ ] README.md + README_ZH.md (bilingual)
- [ ] Complete mkdocs/material documentation site
- [ ] 5-minute quickstart (`swarm init` → `swarm chat`)
- [ ] Docker Compose one-command deployment
- [ ] GitHub Actions CI (pytest + ruff + coverage badge)
- [ ] GitHub Actions CD (PyPI publish on tag)
- [ ] CHANGELOG.md (conventional commits)
- [ ] CONTRIBUTING.md
- [ ] CODE_OF_CONDUCT.md
- [ ] SECURITY.md
- [ ] MIT LICENSE
- [ ] pre-commit hooks (ruff format + check)
- [ ] Test coverage ≥ 80%
- [ ] Logo + social preview image
- [ ] Example projects in `examples/`
- [ ] Semantic versioning policy documented

## 12. Design Decisions Log

| Decision | Rationale |
|----------|-----------|
| 5 states vs nanobot's 7 | COMPACT merged into BUILD (consolidation happens during context assembly). COMMAND handled as hook intercept in BUILD — saves 2 state transitions per turn. |
| Frozen RequestContext vs mutable | Immutability prevents accidental mutation in async call chains. Metadata stored as frozenset ensures hashability for caching. |
| ChromaDB over pure SQLite for memory | Semantic search quality matters for "recall what the user meant, not what they said". SQLite FTS5 cannot do embeddings. |
| AES-encrypted token store | Refresh tokens are long-lived credentials. Plaintext storage is a security risk. Encryption at rest is mandatory for enterprise. |
| Delivery layer separate from channel | hermes proved this pattern: channel handles format conversion, delivery handles reliability. Mixing them creates tangled retry logic. |
| Plugin protocol (not just entry_points) | entry_points cover discovery but not lifecycle (install/enable/disable). A manifest protocol enables tool permission declaration and dependency management. |
| No WebUI | WebUIs add massive complexity (React frontend + WebSocket multiplex + auth). For Feishu enterprise use, the Feishu client IS the UI. CLI for dev/debug. |
