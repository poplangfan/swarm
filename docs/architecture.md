# Swarm Architecture

## Overview

Swarm is a lightweight, concurrency-safe, multi-tenant Feishu AI Agent framework. This document describes the system architecture, component responsibilities, data flow, and key design decisions.

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                      Feishu Open Platform                            │
└────────────────────────────┬────────────────────────────────────────┘
                             │ WebSocket (long connection)
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      Gateway Layer                                   │
│  ┌───────────────┐  ┌───────────────┐  ┌────────────────────────┐  │
│  │ feishu_ws.py  │  │  delivery.py  │  │ feishu_streaming.py    │  │
│  │ WS lifecycle  │  │ Queue/retry   │  │ CardKit engine          │  │
│  └───────┬───────┘  └───────┬───────┘  └────────────────────────┘  │
└──────────┼──────────────────┼──────────────────────────────────────┘
           │                  │
           ▼                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      Message Bus                                     │
│          asyncio.Queue — decouples I/O from agent logic              │
└────────────────────────────┬────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      Agent Layer                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │        AgentLoop State Machine (5 states)                      │  │
│  │  RESTORE → BUILD → RUN → SAVE → RESPOND → DONE                │  │
│  └──────────────────────────┬───────────────────────────────────┘  │
│                             │                                       │
│  ┌──────────────┐  ┌────────┴───────┐  ┌──────────────────────┐   │
│  │ context.py   │  │  runner.py     │  │  subagent.py          │   │
│  │ RequestCtx   │  │ LLM + Tool     │  │  Spawn/pool/monitor   │   │
│  │ (frozen)     │  │ execution loop │  │                       │   │
│  └──────────────┘  └────────────────┘  └──────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      Storage Layer                                   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │
│  │ memory/      │  │ session/     │  │ auth/        │              │
│  │ ChromaDB     │  │ SQLite       │  │ SQLite+encr  │              │
│  │ + Dream      │  │ + Manager    │  │ Token store  │              │
│  └──────────────┘  └──────────────┘  └──────────────┘              │
└─────────────────────────────────────────────────────────────────────┘
```

## Design Principles

### 1. Concurrency Safety First

The framework must handle multiple simultaneous users and group chats without data leakage.

**RequestContext is immutable**: All per-request state is passed explicitly through an immutable `RequestContext` dataclass. Functions that need session state MUST accept `ctx: RequestContext` as their first parameter.

**Per-chat_id isolation**: Every storage backend (SQLite, ChromaDB) partitions data by `chat_id`. One user's data can never leak into another's.

**Async Lock per session**: Each `chat_id` gets its own `asyncio.Lock`. Messages to the same chat are processed serially; messages to different chats process concurrently.

### 2. Explicit Over Implicit

- No global mutable state for request data
- No `os.environ` or `contextvars` for session information
- All dependencies injected through constructors
- Clear ownership and lifecycle for every component

### 3. Minimal Platform Surface

Swarm supports ONLY Feishu. This deliberate constraint allows:

- Deep integration with Feishu-specific features (CardKit, message types, OAuth)
- Smaller codebase (~30K lines vs nanobot's 142K or hermes's 292K)
- No abstraction overhead for multi-platform compatibility
- Faster iteration on Feishu-specific features

### 4. Built for Extension

While the core is Feishu-only, the extension points are designed for growth:

- **Plugin Protocol**: Manifests declare capabilities, permissions, and install steps
- **MCP (Model Context Protocol)**: Both client and server support for tool interoperability
- **Markdown Skills**: User-definable agent behaviors via Markdown files
- **Tool Registry**: Simple registration with auto-discovery

## Component Details

### Gateway Layer

**feishu_ws.py** — WebSocket lifecycle management
- Establishes and maintains WS connection to Feishu
- Automatic reconnection with exponential backoff
- Event signature verification using app_ticket
- Dispatches all Feishu event types to appropriate handlers

**feishu_message.py** — Message content parser
- Handles ALL Feishu message types: text, post, image, audio, file, sticker, interactive, share_chat, system, merge_forward
- Extracts structured content (text + image keys) from each type
- Recursive card content extraction for interactive messages

**feishu_reply.py** — Outbound message construction
- Builds text and interactive card replies
- Manages tenant access token lifecycle
- Handles message threading and reply context

**feishu_streaming.py** — CardKit streaming engine
- Creates streaming message cards
- Sends incremental text updates (deltas) with rate limiting
- Finalizes cards into their final rendered state

### Agent Layer

**AgentLoop** — The core orchestrator
- 5-state machine: RESTORE → BUILD → RUN → SAVE → RESPOND
- Commands (/help, /status, /clear) shortcut from BUILD → RESPOND
- Per-session `asyncio.Lock` for serial execution
- Global `asyncio.Semaphore` for concurrency limiting
- Mid-turn message injection via pending queues
- Checkpoint persistence for crash recovery

**AgentRunner** — LLM conversation loop
- Manages the multi-turn LLM + tool execution cycle
- Handles tool call parsing, execution, and result injection
- Streaming output support with delta callbacks
- Timeout handling at both LLM and tool levels
- Checkpoint callbacks for partial state persistence

**ContextBuilder** — Prompt assembly
- Layers: Identity → Bootstrap files → Tool contract → Memory → Skills → Summary
- Runtime context block appended to user messages (time, channel, chat_id)
- Bootstrap files (AGENTS.md, SOUL.md, USER.md) loaded from workspace

**SubagentManager** — Task delegation
- Spawns independent sub-agents for complex tasks
- Concurrency limit (default: 3) and timeout (default: 300s)
- Results injected back into the parent session
- Subagents cannot recursively spawn

### Storage Layer

**SessionManager** — Conversation persistence
- SQLite-backed per-chat_id session storage
- Message history with configurable limits and token budgets
- Checkpoint save/restore for crash recovery
- Session TTL and cleanup

**Memory System** — Long-term knowledge
- ChromaDB for vector storage with per-chat_id collections
- SQLite for short-term message store
- Dream consolidation: LLM extracts key facts → embeds → stores in ChromaDB
- Hybrid recall: vector similarity + time decay + importance weighting
- Knowledge graph for cross-session entity relationships
- Context compressor for trajectory-preserving truncation

**Auth System** — User identity
- AES-256-GCM encrypted token storage
- Feishu OAuth 2.0 flow with automatic token refresh
- Tools operate with user identity (user_access_token) when available
- Falls back to app identity (tenant_access_token) when not authorized

### Provider Layer

- **AnthropicProvider**: Works with Anthropic API and DeepSeek's Anthropic-compatible endpoint
- **OpenAICompatProvider**: OpenAI API and compatible services (vLLM, Ollama)
- **FallbackProvider**: Chains multiple providers with automatic failover
- **Retry logic**: Exponential backoff with jitter
- **Token counting**: tiktoken-based when available, heuristic fallback

### Events System

- Publish/subscribe event bus for runtime observability
- Event types: session lifecycle, turn lifecycle, tool execution, errors
- Subscribers: structured logging, metrics collection, health monitoring

### Cron System

- APScheduler-based async scheduler
- SQLite persistence (survives restarts)
- Interval and cron-expression triggers
- Natural language task creation via LLM tool

## Data Flow

### Inbound Message Processing

```
1. Feishu WebSocket receives event
2. Event type filter → im.message.receive_v1 only
3. Message deduplication (message_id check)
4. Content extraction (parse_message_content by msg_type)
5. InboundMessage published to MessageBus
6. AgentLoop consumes from bus
7. RESTORE: Load session, restore any checkpoint
8. BUILD: Check for commands, assemble system prompt
9. RUN: LLM call → tool parsing → tool execution → repeat
10. SAVE: Persist messages to session store
11. RESPOND: OutboundMessage published to bus
12. Delivery layer sends via Feishu Reply API
```

### Tool Execution Flow

```
1. LLM returns response with tool_calls
2. For each tool_call:
   a. Parse arguments from JSON
   b. Check permissions against RequestContext
   c. Execute tool with timeout
   d. Format result (truncate if needed)
   e. Inject tool result as new message
3. Call LLM again with updated message list
4. Repeat until LLM returns final content (no tool_calls)
```

### Memory Consolidation Flow

```
1. Messages accumulate in ShortTermMemory (SQLite)
2. When count exceeds consolidation_threshold (default: 20):
   a. Phase 1 (Extraction): LLM reviews recent messages
   b. Phase 1 (Extraction): Outputs structured fact list (JSON)
   c. Phase 2 (Storage): Facts embedded and stored in ChromaDB
   d. Collection named "mem_{chat_id}" for isolation
3. Recall: Hybrid search combining vector similarity, time decay, and importance
```

## Concurrency Model

```
Message Bus
    │
    ├── msg chat_id=A ──► asyncio.Lock("A") ──► AgentLoop._dispatch(msg_A)
    │                                                      │
    ├── msg chat_id=B ──► asyncio.Lock("B") ──► AgentLoop._dispatch(msg_B)
    │                                                      │ (concurrent with A)
    └── msg chat_id=A ──► pending_queue["A"] ─────────────┘ (injected mid-turn)
```

- Each chat_id has its own `asyncio.Lock` — same-chat messages are serialized
- Different chat_ids process concurrently
- Global `asyncio.Semaphore(10)` limits total concurrent turns
- Mid-turn messages for the same chat are queued and injected

## Technology Choices

| Component | Technology | Rationale |
|-----------|-----------|-----------|
| Language | Python 3.11+ | Async support, type hints, ecosystem |
| Config | Pydantic v2 | Validation, env var substitution |
| Logging | structlog | Structured JSON, trace_id propagation |
| HTTP | httpx | Async, HTTP/2, connection pooling |
| LLM SDK | openai + anthropic | Native SDK support for both ecosystems |
| Vector DB | ChromaDB | Embedded, no server needed, per-collection isolation |
| Session DB | SQLite | Zero-config, ACID, per-file isolation |
| Encryption | cryptography (AES-256-GCM) | Industry standard for token storage |
| CLI | Typer + Rich + prompt_toolkit | Modern CLI with Markdown rendering |
| Scheduler | APScheduler | Async, persistent, cron support |
| Feishu SDK | lark-oapi | Official Feishu Open API SDK |
