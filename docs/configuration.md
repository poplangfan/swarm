# Configuration Guide

Swarm uses a YAML configuration file (`config.yaml`) with Pydantic v2 validation. Environment variables can be referenced using `${ENV_VAR}` syntax.

## Quick Start

```bash
# Create from example
swarm init

# Validate your config
swarm validate
```

## Configuration Reference

### LLM Configuration

```yaml
llm:
  # Provider type: "openai", "anthropic", or "custom"
  provider: "anthropic"

  # API base URL (for custom endpoints like DeepSeek)
  base_url: "https://api.deepseek.com/anthropic"

  # API key (use ${ENV_VAR} to avoid hardcoding)
  api_key: "${LLM_API_KEY}"

  # Model identifier
  model: "deepseek-v4-pro"

  # Max tokens per response (1-131072)
  max_tokens: 4096

  # Temperature (0.0-2.0)
  temperature: 0.7

  # Optional fallback chain
  fallback:
    - provider: "openai"
      api_key: "${FALLBACK_API_KEY}"
      model: "gpt-4o-mini"
```

### Supported Providers

| Provider | `provider` value | `base_url` |
|----------|-----------------|------------|
| OpenAI | `openai` | `https://api.openai.com/v1` |
| DeepSeek (Anthropic API) | `anthropic` | `https://api.deepseek.com/anthropic` |
| Anthropic | `anthropic` | (omit for default) |
| Ollama | `openai` | `http://localhost:11434/v1` |
| vLLM | `openai` | `http://localhost:8000/v1` |

### Feishu Configuration

```yaml
feishu:
  # Application credentials from Feishu Open Platform
  app_id: "cli_xxxxxxxxxxxx"
  app_secret: "your_app_secret"

  # Domain: "feishu" (China) or "lark" (International)
  domain: "feishu"

  # Enable CardKit streaming output
  streaming: true

  # Minimum interval between stream updates (seconds)
  stream_edit_interval: 0.5

  # Group chat response policy
  # "mention" — only respond when @mentioned
  # "open" — respond to all messages
  group_policy: "mention"

  # Separate session per group thread/topic
  topic_isolation: true

  # Quote original message in reply
  reply_to_message: false
```

### Auth Configuration

```yaml
auth:
  # Enable user OAuth authorization
  enabled: true

  # OAuth callback URL (LAN IP or localhost works for dev)
  redirect_uri: "http://localhost:9876/oauth/callback"

  # Encryption key for token storage (≥32 chars recommended)
  token_encrypt_key: "${TOKEN_ENCRYPT_KEY}"

  # Requested permission scopes
  scopes:
    - "im:message"          # Send and receive messages
    - "drive:drive:read"    # Read drive files (optional)
    - "docx:document:read"  # Read documents (optional)
```

### Memory Configuration

```yaml
memory:
  # ChromaDB persistence directory
  chroma_path: "./data/chroma"

  # Short-term message retention (days)
  short_term_ttl_days: 7

  # Messages before memory consolidation triggers
  consolidation_threshold: 20

  # Max tokens for LLM context window
  max_context_tokens: 32000

  # Model used for memory extraction (cheaper model recommended)
  dream_model: "gpt-4o-mini"
```

### Logging Configuration

```yaml
logging:
  # Minimum log level: DEBUG, INFO, WARNING, ERROR, CRITICAL
  level: "INFO"

  # JSON format for structured logging
  json_format: true

  # Log file directory
  log_dir: "./data/logs"

  # Retention period (days)
  retention_days: 30

  # Gzip compress rotated logs
  compress: true

  # Separate audit log for compliance
  audit_enabled: true

  # Separate error log file
  error_separate: true
```

### Tools Configuration

```yaml
tools:
  # Web search tool
  web_search:
    enabled: true
    provider: "duckduckgo"  # or "bing"

  # Subagent configuration
  subagent:
    max_concurrent: 3        # 1-10
    timeout_seconds: 300     # ≥30

  # Code execution sandbox
  sandbox:
    enabled: false           # Off by default
```

### Cron Configuration

```yaml
cron:
  jobs:
    memory_consolidation:
      interval_minutes: 30   # Every 30 minutes
    soul_evolution:
      interval_minutes: 240  # Every 4 hours
```

## Environment Variables

All `${ENV_VAR}` placeholders in the config are resolved from the environment at startup. The syntax supports defaults:

```yaml
api_key: "${LLM_API_KEY:-sk-default-key}"
```

If `LLM_API_KEY` is not set, the fallback value `sk-default-key` is used.

## Config File Location

Swarm searches for `config.yaml` in this order:

1. Explicit path: `swarm ws --config /path/to/config.yaml`
2. `SWARM_CONFIG` environment variable
3. `./config.yaml` (current working directory)
4. `~/.swarm/config.yaml` (user home directory)

## Validation

```bash
# Validate configuration without starting
swarm validate

# With custom path
swarm validate --config /path/to/config.yaml
```

Validation errors include specific field locations and expected types, making debugging straightforward.

## Production Deployment

For production, consider:

1. **Use environment variables** for all secrets (API keys, app secrets)
2. **Enable JSON logging** for log aggregation systems
3. **Set appropriate log levels** (INFO or WARNING)
4. **Configure audit logging** for compliance
5. **Use a process manager** (systemd, supervisor) to keep `swarm ws` running
6. **Set up log rotation** (built-in) and monitoring

## Example: Development Config

```yaml
llm:
  provider: "anthropic"
  base_url: "https://api.deepseek.com/anthropic"
  api_key: "${LLM_API_KEY}"
  model: "deepseek-v4-pro"

feishu:
  app_id: "${FEISHU_APP_ID}"
  app_secret: "${FEISHU_APP_SECRET}"

logging:
  level: "DEBUG"
  json_format: false  # Human-readable for development
```

## Example: Production Config

```yaml
llm:
  provider: "anthropic"
  api_key: "${LLM_API_KEY}"
  model: "claude-sonnet-4-6"
  fallback:
    - provider: "openai"
      api_key: "${FALLBACK_OPENAI_KEY}"
      model: "gpt-4o-mini"

feishu:
  app_id: "${FEISHU_APP_ID}"
  app_secret: "${FEISHU_APP_SECRET}"
  group_policy: "mention"

auth:
  token_encrypt_key: "${TOKEN_ENCRYPT_KEY}"

logging:
  level: "INFO"
  json_format: true
  retention_days: 90
  audit_enabled: true
```
