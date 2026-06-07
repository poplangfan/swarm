# Logging & Monitoring

Swarm uses structlog for structured JSON logging with automatic rotation and compression.

## Log Files

```
data/logs/
├── swarm-2026-06-07.log       # Today's application logs
├── swarm-2026-06-06.log.gz    # Yesterday (compressed)
├── swarm-error-2026-06-07.log # Today's error logs (ERROR+)
├── swarm-error-2026-06-06.log.gz
├── audit-2026-06-07.log       # Today's audit trail
└── audit-2026-06-06.log.gz
```

## Log Format

```json
{
  "timestamp": "2026-06-07T14:23:45.123Z",
  "level": "info",
  "event": "turn_completed",
  "trace_id": "a1b2c3d4-e5f6",
  "chat_id": "oc_xxx",
  "user_id": "ou_yyy",
  "latency_ms": 1234,
  "tools_used": ["web_search"],
  "stop_reason": "end_turn",
  "logger": "swarm.agent.loop"
}
```

## Configuration

```yaml
logging:
  level: "INFO"              # DEBUG, INFO, WARNING, ERROR, CRITICAL
  json_format: true          # Structured JSON for log aggregation
  log_dir: "./data/logs"
  retention_days: 30         # Auto-delete after this many days
  compress: true             # gzip rotated logs
  audit_enabled: true        # Separate audit log
  error_separate: true       # Separate error log
```

## Trace ID

Every request gets a unique `trace_id` that appears in all log entries for that request. Use it to trace a message through the entire pipeline:

```bash
grep "trace_id=abc123" data/logs/swarm-*.log
```

This shows every state transition, tool call, and LLM interaction for that request.

## Audit Logging

The audit log records all user-identifiable actions for compliance:

- Who sent what message
- Which tools were used
- Token refresh events
- Session lifecycle events
- Error occurrences

Audit logs are retained twice as long as regular logs (60 days by default).

## Log Rotation

- **Schedule**: Daily at midnight
- **Compression**: Rotated logs are gzipped automatically
- **Retention**: Configurable (default: 30 days for app, 60 for audit)
- **Cleanup**: Old logs are deleted when they exceed retention

## Querying Logs

### By Time Range

```bash
# Today's errors
cat data/logs/swarm-error-$(date +%Y-%m-%d).log

# Recent activity
zcat data/logs/swarm-$(date -d yesterday +%Y-%m-%d).log.gz | head -20
```

### By Content

```bash
# Find all turn completions
grep "turn_completed" data/logs/swarm-*.log

# Find errors with stack traces
grep -A 5 "error_occurred" data/logs/swarm-*.log

# Find activity for a specific user
grep "user_id.*ou_xxx" data/logs/swarm-*.log
```

### Structured Analysis

Since logs are JSON:

```python
import json

with open("data/logs/swarm-2026-06-07.log") as f:
    for line in f:
        entry = json.loads(line)
        if entry.get("event") == "turn_completed":
            print(f"Turn: {entry['trace_id']} latency={entry.get('latency_ms', '?')}ms")
```

## Metrics

Swarm's events system collects runtime metrics:

| Metric | Description |
|--------|-------------|
| `turn_latency_ms` | Wall clock time from message receipt to response |
| `llm_latency_ms` | Time spent waiting for LLM API |
| `tool_latency_ms` | Per-tool execution time |
| `tokens_used` | Input + output tokens per turn |
| `active_sessions` | Current number of active sessions |
| `error_rate` | Errors per time window |

Access via the events subscriber:

```python
from swarm.events.subscribers.metrics import MetricsCollector

collector = MetricsCollector()
summary = collector.get_summary()
print(f"Active sessions: {summary['active_sessions']}")
print(f"Avg latency: {summary['avg_turn_latency_ms']}ms")
```

## Production Monitoring

### Docker

```bash
docker compose logs -f  # Follow all logs
docker compose logs --tail=100  # Last 100 lines
```

### systemd

```bash
journalctl -u swarm -f  # Follow service logs
journalctl -u swarm --since "1 hour ago"
```

### Health Checks

Monitor these signals:
1. **Process uptime** — Is `swarm ws` running?
2. **Error rate** — Are errors increasing?
3. **Response latency** — Are turns getting slower?
4. **Disk usage** — Is the log directory filling up?
5. **Memory usage** — Is there a memory leak?

## Alerting

Consider setting up alerts for:
- Process down (should auto-restart via systemd)
- Error rate > 5% of requests
- Average latency > 10 seconds
- Disk usage > 80%
- ChromaDB corruption errors
