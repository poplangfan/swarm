# Changelog

All notable changes to Swarm will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] — 2026-06-07

### Added
- Initial release of Swarm framework
- 5-state AgentLoop (RESTORE → BUILD → RUN → SAVE → RESPOND)
- Immutable RequestContext for concurrency-safe multi-tenant isolation
- Per-chat_id asyncio.Lock for serial session processing
- ChromaDB vector memory with per-chat_id collections
- SQLite short-term message store
- Dream two-phase memory consolidation (LLM extraction + vector storage)
- Context compressor with trajectory-preserving truncation
- Knowledge graph for cross-session entity relationships
- Hybrid memory recall (vector similarity + time decay + importance)
- Feishu WebSocket long connection support
- Full Feishu message type parser (text, post, image, audio, file, sticker, interactive, share_chat, merge_forward)
- CardKit streaming output engine
- Interactive card action handling
- Feishu OAuth 2.0 user authorization flow
- AES-256-GCM encrypted token storage with auto-refresh
- User identity injection for tool operations
- Async message bus (asyncio.Queue)
- OpenAI-compatible provider (supports vLLM, Ollama, custom endpoints)
- Anthropic provider (supports DeepSeek Anthropic-compatible API)
- Provider fallback chain with automatic failover
- Exponential backoff retry with jitter
- Token counting (tiktoken-based + heuristic fallback)
- Tool registry with auto-discovery
- Tool permission system with declarative access control
- Web search tool (DuckDuckGo)
- Web fetch tool (URL content extraction)
- Feishu message operations tool (send, react)
- Feishu file operations tool (list, info)
- Cron management tool (create, list, delete)
- System command tool (help, status)
- Subagent system with concurrency limiting and timeout
- Markdown Skills loader with frontmatter support
- 10 built-in skills (base-assistant, calendar, summary, translator, code-review, reminder, customer-support, data-analysis, meeting-notes, feishu-docs)
- MCP client for connecting to external MCP servers
- MCP server for exposing Swarm tools
- Plugin manifest protocol with lifecycle management
- Plugin loader (filesystem + setuptools entry points)
- Publish/subscribe event bus for runtime observability
- Metrics collector for monitoring (latency, throughput, errors)
- APScheduler-based cron with SQLite persistence
- Natural language → cron expression parser
- Persistent state store with snapshots and migration
- Outbound message delivery layer (per-chat queues, rate limiting, retry)
- Interactive CLI with Rich and prompt_toolkit
- Commands: `swarm chat`, `swarm ws`, `swarm init`, `swarm validate`, `swarm version`
- structlog-based structured JSON logging
- Log rotation with gzip compression
- Separate audit log and error log
- Configurable log retention
- Pydantic v2 configuration schema with YAML loader
- ${ENV_VAR} substitution in config files
- Graceful shutdown with checkpoint preservation
- Docker deployment with docker-compose
- Systemd and supervisor service templates
- 220+ unit and integration tests
- Comprehensive documentation
