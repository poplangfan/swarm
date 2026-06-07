# Swarm Framework Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a 55k-60k line concurrency-safe multi-tenant Feishu AI Agent framework from scratch, inspired by nanobot/hermes-agent designs but independently implemented.

**Architecture:** Phase 0 (skeleton) → Phase 1 (providers) → Phase 2 (agent core) → Phase 3 (memory) → Phase 4 (tools) → Phase 5 (gateway) → Phase 6 (auth) → Phase 7 (horizontal features) → Phase 8 (CLI) → Phase 9 (skills/examples) → Phase 10 (docs/CI/release).

**Tech Stack:** Python 3.11+, asyncio, Pydantic v2, structlog, ChromaDB, SQLite, lark-oapi, APScheduler, Typer, Rich, prompt_toolkit, pytest

---

### Task 0: Project Skeleton

**Files:**
- Create: `swarm/pyproject.toml`
- Create: `swarm/__init__.py`
- Create: `swarm/__main__.py`
- Create: `swarm/.gitignore`
- Create: `swarm/config.yaml.example`

- [ ] **Step 1: Create pyproject.toml with dependencies**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "swarm-agent"
version = "0.1.0"
description = "Lightweight, concurrency-safe, multi-tenant Feishu AI Agent framework"
readme = "README.md"
license = {text = "MIT"}
requires-python = ">=3.11"
authors = [{name = "Swarm Contributors"}]
keywords = ["feishu", "lark", "ai-agent", "llm", "chatbot"]
classifiers = [
    "Development Status :: 3 - Alpha",
    "Intended Audience :: Developers",
    "License :: OSI Approved :: MIT License",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
    "Programming Language :: Python :: 3.13",
]

dependencies = [
    "pydantic>=2.0",
    "pyyaml>=6.0",
    "structlog>=24.0",
    "httpx>=0.27",
    "chromadb>=0.5",
    "lark-oapi>=1.3",
    "apscheduler>=3.10",
    "cryptography>=42.0",
    "tiktoken>=0.7",
    "typer>=0.12",
    "rich>=13.0",
    "prompt-toolkit>=3.0",
    "jinja2>=3.1",
    "aiofiles>=24.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
    "pytest-cov>=5.0",
    "ruff>=0.5",
]

[project.scripts]
swarm = "swarm.cli.main:app"

[project.entry-points."swarm.plugins"]
# Plugins register here

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I", "N", "W"]
ignore = ["E501"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

- [ ] **Step 2: Create swarm/__init__.py**

```python
"""Swarm — Lightweight, concurrency-safe, multi-tenant Feishu AI Agent framework."""

__version__ = "0.1.0"
__logo__ = r"""
   _____
  / ___/      __  ______ ___  ____ ___  ___
  \__ \| | /| / / / __ `__ \/ __ `__ \/ _ \
 ___/ /| |/ |/ / / / / / / / / / / / /  __/
/____/ |__/|__/ /_/ /_/ /_/_/ /_/ /_/\___/
"""
```

- [ ] **Step 3: Create swarm/__main__.py**

```python
"""Allow running as: python -m swarm"""

from swarm.cli.main import app

if __name__ == "__main__":
    app()
```

- [ ] **Step 4: Create .gitignore**

```gitignore
__pycache__/
*.py[cod]
*.egg-info/
dist/
build/
.venv/
venv/
.env
data/
*.log
*.log.gz
.pytest_cache/
.coverage
htmlcov/
.ruff_cache/
```

- [ ] **Step 5: Create config.yaml.example**

```yaml
# Swarm configuration — copy to config.yaml and fill in your values
# All ${ENV_VAR} placeholders are resolved from environment at startup

llm:
  provider: "openai"
  base_url: "https://api.openai.com/v1"
  api_key: "${LLM_API_KEY}"
  model: "gpt-4o"
  max_tokens: 4096
  temperature: 0.7

feishu:
  app_id: "${FEISHU_APP_ID}"
  app_secret: "${FEISHU_APP_SECRET}"
  domain: "feishu"
  streaming: true
  group_policy: "mention"

auth:
  enabled: true
  token_encrypt_key: "${TOKEN_ENCRYPT_KEY}"
  scopes:
    - "im:message"

memory:
  chroma_path: "./data/chroma"
  consolidation_threshold: 20

logging:
  level: "INFO"
  json_format: true
  log_dir: "./data/logs"
  retention_days: 30
```

- [ ] **Step 6: Initialize git and install**

```bash
cd /home/ubuntu/code/project/swarm
git init
git add -A
git commit -m "chore: initialize project skeleton"

cd swarm
python -m venv venv
source venv/bin/activate
pip install -e .
pip install -e ".[dev]"
```

---

### Task 1: Config System

**Files:**
- Create: `swarm/swarm/config/__init__.py`
- Create: `swarm/swarm/config/schema.py`
- Create: `swarm/swarm/config/loader.py`
- Create: `swarm/swarm/config/paths.py`

- [ ] **Step 1: Write config schema tests**

Create `swarm/tests/test_config.py`:

```python
import pytest
from pydantic import ValidationError
from swarm.config.schema import SwarmConfig, LLMConfig, FeishuConfig


class TestLLMConfig:
    def test_minimal_config(self):
        cfg = LLMConfig(api_key="sk-test", base_url="https://api.openai.com/v1")
        assert cfg.provider == "openai"
        assert cfg.model == "gpt-4o"
        assert cfg.max_tokens == 4096

    def test_missing_api_key_raises(self):
        with pytest.raises(ValidationError):
            LLMConfig(base_url="https://api.openai.com/v1")


class TestFeishuConfig:
    def test_domain_validation(self):
        cfg = FeishuConfig(app_id="x", app_secret="y", domain="feishu")
        assert cfg.domain == "feishu"

    def test_invalid_domain_raises(self):
        with pytest.raises(ValidationError):
            FeishuConfig(app_id="x", app_secret="y", domain="invalid")


class TestSwarmConfig:
    def test_load_from_dict(self):
        data = {
            "llm": {"api_key": "sk-test"},
            "feishu": {"app_id": "x", "app_secret": "y"},
        }
        cfg = SwarmConfig.model_validate(data)
        assert cfg.llm.api_key == "sk-test"
        assert cfg.feishu.app_id == "x"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/ubuntu/code/project/swarm/swarm
pytest tests/test_config.py -v
```

Expected: Import errors — modules don't exist yet.

- [ ] **Step 3: Implement config/schema.py**

```python
"""Pydantic v2 configuration schema for Swarm."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


class LLMConfig(BaseModel):
    """LLM provider configuration."""

    provider: Literal["openai", "anthropic", "custom"] = "openai"
    base_url: str = "https://api.openai.com/v1"
    api_key: str
    model: str = "gpt-4o"
    max_tokens: int = Field(default=4096, ge=1)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    fallback: list[dict] = Field(default_factory=list)


class FeishuConfig(BaseModel):
    """Feishu/Lark platform configuration."""

    app_id: str
    app_secret: str
    domain: Literal["feishu", "lark"] = "feishu"
    streaming: bool = True
    stream_edit_interval: float = Field(default=0.5, ge=0.1)
    group_policy: Literal["mention", "open"] = "mention"
    topic_isolation: bool = True
    reply_to_message: bool = False


class AuthConfig(BaseModel):
    """User OAuth authorization configuration."""

    enabled: bool = True
    redirect_uri: str = "http://localhost:9876/oauth/callback"
    token_encrypt_key: str = ""
    scopes: list[str] = Field(default_factory=lambda: ["im:message"])


class MemoryConfig(BaseModel):
    """Memory system configuration."""

    chroma_path: str = "./data/chroma"
    short_term_ttl_days: int = Field(default=7, ge=1)
    consolidation_threshold: int = Field(default=20, ge=5)
    max_context_tokens: int = Field(default=32000, ge=1024)
    dream_model: str = "gpt-4o-mini"


class CronJobConfig(BaseModel):
    """Single cron job configuration."""

    interval_minutes: int = Field(default=30, ge=1)


class CronConfig(BaseModel):
    """Cron scheduler configuration."""

    jobs: dict[str, CronJobConfig] = Field(default_factory=lambda: {
        "memory_consolidation": CronJobConfig(interval_minutes=30),
        "soul_evolution": CronJobConfig(interval_minutes=240),
    })


class LoggingConfig(BaseModel):
    """Logging system configuration."""

    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    json_format: bool = True
    log_dir: str = "./data/logs"
    retention_days: int = Field(default=30, ge=1)
    compress: bool = True
    audit_enabled: bool = True
    error_separate: bool = True


class WebSearchConfig(BaseModel):
    """Web search tool configuration."""

    enabled: bool = True
    provider: Literal["duckduckgo", "bing"] = "duckduckgo"


class SubagentConfig(BaseModel):
    """Subagent configuration."""

    max_concurrent: int = Field(default=3, ge=1, le=10)
    timeout_seconds: int = Field(default=300, ge=30)


class SandboxConfig(BaseModel):
    """Code execution sandbox configuration."""

    enabled: bool = False


class ToolsConfig(BaseModel):
    """Tools configuration."""

    web_search: WebSearchConfig = Field(default_factory=WebSearchConfig)
    subagent: SubagentConfig = Field(default_factory=SubagentConfig)
    sandbox: SandboxConfig = Field(default_factory=SandboxConfig)


class SwarmConfig(BaseModel):
    """Root Swarm configuration."""

    llm: LLMConfig
    feishu: FeishuConfig
    auth: AuthConfig = Field(default_factory=AuthConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    cron: CronConfig = Field(default_factory=CronConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    tools: ToolsConfig = Field(default_factory=ToolsConfig)
```

- [ ] **Step 4: Create config/__init__.py and config/paths.py**

```python
# swarm/config/__init__.py
from swarm.config.schema import SwarmConfig

__all__ = ["SwarmConfig"]
```

```python
# swarm/config/paths.py
"""XDG-compatible path resolution for Swarm data directories."""

from pathlib import Path


def config_dir() -> Path:
    """Return the user config directory (~/.swarm)."""
    path = Path.home() / ".swarm"
    path.mkdir(parents=True, exist_ok=True)
    return path


def data_dir() -> Path:
    """Return the data directory (./data relative to cwd, or configured)."""
    path = Path.cwd() / "data"
    path.mkdir(parents=True, exist_ok=True)
    return path


def log_dir() -> Path:
    """Return the log directory."""
    path = data_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def chroma_dir() -> Path:
    """Return the ChromaDB persistence directory."""
    path = data_dir() / "chroma"
    path.mkdir(parents=True, exist_ok=True)
    return path
```

- [ ] **Step 5: Implement config/loader.py**

```python
"""Configuration loader: YAML parsing with ${ENV_VAR} substitution."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml

from swarm.config.schema import SwarmConfig

_ENV_VAR_RE = re.compile(r"\$\{([^}]+)\}")


def _resolve_env_vars(value: Any) -> Any:
    """Recursively substitute ${ENV_VAR} placeholders in strings."""
    if isinstance(value, str):
        def _replace(match: re.Match) -> str:
            var = match.group(1)
            default = None
            if ":-" in var:
                var, default = var.split(":-", 1)
            result = os.environ.get(var.strip())
            if result is not None:
                return result
            if default is not None:
                return default.strip()
            return match.group(0)  # Leave unresolved placeholder
        return _ENV_VAR_RE.sub(_replace, value)
    elif isinstance(value, dict):
        return {k: _resolve_env_vars(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [_resolve_env_vars(item) for item in value]
    return value


def load_config(path: str | Path | None = None) -> SwarmConfig:
    """Load and validate configuration from a YAML file.

    Searches in order:
    1. Explicit path argument
    2. SWARM_CONFIG environment variable
    3. ./config.yaml
    4. ~/.swarm/config.yaml
    """
    if path is not None:
        config_path = Path(path)
    elif (env_path := os.environ.get("SWARM_CONFIG")):
        config_path = Path(env_path)
    else:
        candidates = [
            Path.cwd() / "config.yaml",
            Path.home() / ".swarm" / "config.yaml",
        ]
        config_path = next((p for p in candidates if p.exists()), candidates[0])

    if not config_path.exists():
        raise FileNotFoundError(
            f"Config file not found at {config_path}. "
            "Copy config.yaml.example to config.yaml and fill in your values."
        )

    with open(config_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    if raw is None:
        raise ValueError(f"Config file {config_path} is empty")

    resolved = _resolve_env_vars(raw)
    return SwarmConfig.model_validate(resolved)
```

- [ ] **Step 6: Run tests**

```bash
pytest tests/test_config.py -v
```

Expected: All tests pass.

- [ ] **Step 7: Commit**

```bash
git add swarm/config/ tests/test_config.py
git commit -m "feat: add config system (Pydantic v2 schema + YAML loader)"
```

---

### Task 2: Logging System

**Files:**
- Create: `swarm/swarm/logging_/__init__.py`
- Create: `swarm/swarm/logging_/setup.py`
- Create: `swarm/swarm/logging_/handlers.py`
- Create: `swarm/swarm/logging_/trace.py`
- Create: `swarm/tests/test_logging.py`

- [ ] **Step 1: Write logging tests**

```python
# tests/test_logging.py
import json
import os
import tempfile
from pathlib import Path

import pytest
from swarm.logging_.setup import setup_logging
from swarm.logging_.trace import TraceContext, get_trace_id, set_trace_id


class TestTraceContext:
    def test_set_and_get_trace_id(self):
        ctx = TraceContext()
        ctx.set("trace-123")
        assert ctx.get() == "trace-123"

    def test_trace_id_defaults_to_none(self):
        ctx = TraceContext()
        assert ctx.get() is None

    def test_context_isolation(self):
        ctx1 = TraceContext()
        ctx2 = TraceContext()
        ctx1.set("aaa")
        ctx2.set("bbb")
        assert ctx1.get() == "aaa"
        assert ctx2.get() == "bbb"


class TestLoggingSetup:
    def test_console_handler_created(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            setup_logging(
                level="DEBUG",
                json_format=False,
                log_dir=tmpdir,
            )
            import structlog
            log = structlog.get_logger()
            log.info("test_message", key="value")

            # Verify log file was created
            log_files = list(Path(tmpdir).glob("swarm-*.log"))
            assert len(log_files) > 0

    def test_json_format(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            setup_logging(
                level="INFO",
                json_format=True,
                log_dir=tmpdir,
            )
            import structlog
            log = structlog.get_logger()
            log.info("test_json", foo="bar")

            log_files = list(Path(tmpdir).glob("swarm-*.log"))
            content = log_files[0].read_text()
            assert '"event": "test_json"' in content
            assert '"foo": "bar"' in content
```

- [ ] **Step 2: Implement logging_/trace.py**

```python
"""Trace ID management for request-level tracing through all subsystems."""

from __future__ import annotations

import uuid
from contextvars import ContextVar
from typing import Iterator

_trace_id_var: ContextVar[str | None] = ContextVar("trace_id", default=None)


class TraceContext:
    """Context manager for trace ID propagation."""

    def set(self, trace_id: str | None = None) -> str:
        """Set the trace ID for the current context. Returns the trace ID."""
        tid = trace_id or str(uuid.uuid4())
        _trace_id_var.set(tid)
        return tid

    def get(self) -> str | None:
        """Get the current trace ID."""
        return _trace_id_var.get()

    def ensure(self) -> str:
        """Get current trace ID, generating one if none exists."""
        tid = _trace_id_var.get()
        if tid is None:
            tid = str(uuid.uuid4())
            _trace_id_var.set(tid)
        return tid


def get_trace_id() -> str | None:
    """Get the current trace_id from context."""
    return _trace_id_var.get()


def set_trace_id(trace_id: str) -> None:
    """Set the trace_id for the current context."""
    _trace_id_var.set(trace_id)


def new_trace_id() -> str:
    """Generate a new trace_id and set it. Returns the new ID."""
    tid = str(uuid.uuid4())
    _trace_id_var.set(tid)
    return tid
```

- [ ] **Step 3: Implement logging_/handlers.py**

```python
"""Log handlers: timed rotation + gzip compression + cleanup."""

from __future__ import annotations

import gzip
import logging
import os
import shutil
import time
from datetime import datetime, timedelta
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Any


class CompressingTimedRotatingFileHandler(TimedRotatingFileHandler):
    """TimedRotatingFileHandler that gzips rotated log files."""

    def __init__(
        self,
        log_dir: str,
        retention_days: int = 30,
        when: str = "midnight",
        interval: int = 1,
        backup_count: int = 30,
        encoding: str = "utf-8",
    ):
        self._log_dir = Path(log_dir)
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._retention_days = retention_days

        filename = str(self._log_dir / "swarm.log")
        super().__init__(
            filename=filename,
            when=when,
            interval=interval,
            backupCount=backup_count,
            encoding=encoding,
        )
        self.suffix = "%Y-%m-%d"

    def rotation_filename(self, default_name: str) -> str:
        """Append date suffix for rotated files."""
        base = default_name.replace(".log", "")
        date_str = datetime.now().strftime("%Y-%m-%d")
        return f"{base}-{date_str}.log"

    def rotate(self, source: str, dest: str) -> None:
        """Rotate the current log file."""
        super().rotate(source, dest)
        # Compress any uncompressed rotated files
        for f in self._log_dir.glob("swarm-*.log"):
            if f.name == Path(source).name:
                continue
            gz_path = f.with_suffix(f.suffix + ".gz")
            if not gz_path.exists() and f.exists():
                with open(f, "rb") as f_in:
                    with gzip.open(str(gz_path), "wb") as f_out:
                        shutil.copyfileobj(f_in, f_out)
                f.unlink()
        # Clean up old logs
        self._cleanup_old_logs()

    def _cleanup_old_logs(self) -> None:
        """Remove logs older than retention_days."""
        cutoff = time.time() - (self._retention_days * 86400)
        for pattern in ["swarm-*.log.gz", "swarm-error-*.log.gz",
                         "audit-*.log.gz", "swarm-*.log", "swarm-error-*.log",
                         "audit-*.log"]:
            for f in self._log_dir.glob(pattern):
                if f.stat().st_mtime < cutoff:
                    f.unlink()
```

- [ ] **Step 4: Implement logging_/setup.py**

```python
"""structlog configuration for Swarm."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

import structlog

from swarm.logging_.handlers import CompressingTimedRotatingFileHandler
from swarm.logging_.trace import get_trace_id


def _add_trace_id(_logger: Any, _method_name: str, event_dict: dict) -> dict:
    """Add trace_id to every log event if available."""
    tid = get_trace_id()
    if tid:
        event_dict["trace_id"] = tid
    return event_dict


def setup_logging(
    level: str = "INFO",
    json_format: bool = True,
    log_dir: str = "./data/logs",
    retention_days: int = 30,
    compress: bool = True,
    audit_enabled: bool = True,
    error_separate: bool = True,
) -> None:
    """Configure structlog with file and console output.

    Args:
        level: Minimum log level.
        json_format: Use JSON formatting for file logs.
        log_dir: Directory for log files.
        retention_days: Days to retain logs.
        compress: Gzip rotated logs.
        audit_enabled: Write separate audit log.
        error_separate: Separate ERROR+ logs.
    """
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    level_num = getattr(logging, level.upper(), logging.INFO)

    # Shared processors
    shared_processors = [
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        _add_trace_id,
    ]

    # JSON renderer for file output
    json_renderer = structlog.processors.JSONRenderer()

    # Console renderer
    console_renderer = structlog.dev.ConsoleRenderer()

    # Configure standard logging for file handlers
    root_logger = logging.getLogger()
    root_logger.setLevel(level_num)

    # Remove any existing handlers
    for h in root_logger.handlers[:]:
        root_logger.removeHandler(h)

    # Main application log (file)
    if json_format:
        app_handler = CompressingTimedRotatingFileHandler(
            log_dir=str(log_path),
            retention_days=retention_days,
        )
        app_handler.setLevel(level_num)
        app_handler.setFormatter(logging.Formatter("%(message)s"))
        root_logger.addHandler(app_handler)

    # Console handler
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(level_num)
    console_handler.setFormatter(logging.Formatter("%(message)s"))
    root_logger.addHandler(console_handler)

    # Error log (separate file)
    if error_separate:
        error_handler = CompressingTimedRotatingFileHandler(
            log_dir=str(log_path),
            retention_days=retention_days,
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(logging.Formatter("%(message)s"))
        # Override filename pattern for errors
        error_handler.baseFilename = str(log_path / "swarm-error.log")
        root_logger.addHandler(error_handler)

    # Audit log
    if audit_enabled:
        audit_handler = CompressingTimedRotatingFileHandler(
            log_dir=str(log_path),
            retention_days=retention_days * 2,  # Audit logs kept longer
        )
        audit_handler.setLevel(logging.INFO)
        audit_handler.setFormatter(logging.Formatter("%(message)s"))
        audit_handler.baseFilename = str(log_path / "audit.log")
        audit_logger = logging.getLogger("swarm.audit")
        audit_logger.addHandler(audit_handler)
        audit_logger.propagate = False

    # Configure structlog
    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
```

- [ ] **Step 5: Create logging_/__init__.py**

```python
"""Logging system for Swarm — structlog + rotation + compression + audit."""

from swarm.logging_.setup import setup_logging
from swarm.logging_.trace import TraceContext, get_trace_id, new_trace_id, set_trace_id

__all__ = [
    "setup_logging",
    "TraceContext",
    "get_trace_id",
    "set_trace_id",
    "new_trace_id",
]
```

- [ ] **Step 6: Run tests**

```bash
pytest tests/test_logging.py -v
```

Expected: All tests pass.

- [ ] **Step 7: Commit**

```bash
git add swarm/logging_/ tests/test_logging.py
git commit -m "feat: add logging system (structlog + rotation + compression + audit)"
```

---

### Task 3: Message Bus

**Files:**
- Create: `swarm/swarm/bus/__init__.py`
- Create: `swarm/swarm/bus/queue.py`
- Create: `swarm/tests/test_bus.py`

- [ ] **Step 1: Write bus tests**

```python
# tests/test_bus.py
import asyncio
import pytest
from swarm.bus.queue import MessageBus, InboundMessage, OutboundMessage


def make_msg(chat_id: str, content: str = "hello") -> InboundMessage:
    return InboundMessage(
        channel="feishu",
        sender_id="user_1",
        chat_id=chat_id,
        content=content,
    )


class TestMessageBus:
    @pytest.mark.asyncio
    async def test_publish_and_consume(self):
        bus = MessageBus()
        msg = make_msg("chat_A")
        await bus.publish_inbound(msg)

        consumed = await bus.consume_inbound()
        assert consumed.chat_id == "chat_A"
        assert consumed.content == "hello"

    @pytest.mark.asyncio
    async def test_fifo_ordering(self):
        bus = MessageBus()
        await bus.publish_inbound(make_msg("A", "first"))
        await bus.publish_inbound(make_msg("B", "second"))
        await bus.publish_inbound(make_msg("C", "third"))

        m1 = await bus.consume_inbound()
        m2 = await bus.consume_inbound()
        m3 = await bus.consume_inbound()

        assert m1.content == "first"
        assert m2.content == "second"
        assert m3.content == "third"

    @pytest.mark.asyncio
    async def test_stop_accepting(self):
        bus = MessageBus()
        bus.stop_accepting()
        await bus.publish_inbound(make_msg("A"))  # Should not raise

    @pytest.mark.asyncio
    async def test_outbound_publish(self):
        bus = MessageBus()
        out = OutboundMessage(channel="feishu", chat_id="chat_A", content="reply")
        await bus.publish_outbound(out)
        # Outbound messages are consumed by channel adapters
        # Just verify it doesn't error

    @pytest.mark.asyncio
    async def test_message_metadata(self):
        bus = MessageBus()
        msg = InboundMessage(
            channel="feishu",
            sender_id="user_1",
            chat_id="chat_A",
            content="hi",
            metadata={"message_id": "msg_001", "chat_type": "p2p"},
        )
        await bus.publish_inbound(msg)
        consumed = await bus.consume_inbound()
        assert consumed.metadata["message_id"] == "msg_001"
        assert consumed.metadata["chat_type"] == "p2p"
```

- [ ] **Step 2: Implement bus/queue.py**

```python
"""Async message bus — decouples I/O channels from the agent core."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any


@dataclass
class InboundMessage:
    """A message received from an external channel."""
    channel: str
    sender_id: str
    chat_id: str
    content: str
    media: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    session_key_override: str | None = None

    @property
    def session_key(self) -> str:
        """Derive the session key: {channel}:{chat_id}."""
        return self.session_key_override or f"{self.channel}:{self.chat_id}"


@dataclass
class OutboundMessage:
    """A message to be sent to an external channel."""
    channel: str
    chat_id: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)


class MessageBus:
    """Async message bus using asyncio.Queue.

    Inbound messages from channels are published here and consumed
    by the AgentLoop. Outbound messages are published by the AgentLoop
    and consumed by channel adapters.
    """

    def __init__(self, maxsize: int = 1024):
        self._inbound: asyncio.Queue[InboundMessage] = asyncio.Queue(maxsize=maxsize)
        self._outbound: asyncio.Queue[OutboundMessage] = asyncio.Queue(maxsize=maxsize)
        self._accepting: bool = True

    async def publish_inbound(self, msg: InboundMessage) -> None:
        """Publish an inbound message. Non-blocking if full."""
        if not self._accepting:
            return
        try:
            self._inbound.put_nowait(msg)
        except asyncio.QueueFull:
            pass

    async def consume_inbound(self) -> InboundMessage:
        """Wait for and return the next inbound message."""
        return await self._inbound.get()

    async def publish_outbound(self, msg: OutboundMessage) -> None:
        """Publish an outbound message."""
        try:
            self._outbound.put_nowait(msg)
        except asyncio.QueueFull:
            pass

    async def consume_outbound(self) -> OutboundMessage:
        """Wait for and return the next outbound message."""
        return await self._outbound.get()

    def stop_accepting(self) -> None:
        """Reject new inbound messages (used during graceful shutdown)."""
        self._accepting = False

    @property
    def inbound_size(self) -> int:
        return self._inbound.qsize()

    @property
    def outbound_size(self) -> int:
        return self._outbound.qsize()
```

- [ ] **Step 3: Create bus/__init__.py**

```python
"""Message bus — decouples I/O from agent logic."""

from swarm.bus.queue import InboundMessage, MessageBus, OutboundMessage

__all__ = ["MessageBus", "InboundMessage", "OutboundMessage"]
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_bus.py -v
```

Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
git add swarm/bus/ tests/test_bus.py
git commit -m "feat: add async message bus (asyncio.Queue decoupling)"
```

---

### Task 4: Utils Module

**Files:**
- Create: `swarm/swarm/utils/__init__.py`
- Create: `swarm/swarm/utils/helpers.py`
- Create: `swarm/swarm/utils/text.py`
- Create: `swarm/swarm/utils/template.py`
- Create: `swarm/swarm/utils/media.py`
- Create: `swarm/tests/test_utils.py`

- [ ] **Step 1: Write utils tests**

```python
# tests/test_utils.py
from swarm.utils.text import truncate_text, current_time_str
from swarm.utils.helpers import safe_filename


class TestTruncateText:
    def test_short_text_unchanged(self):
        assert truncate_text("hello", 100) == "hello"

    def test_long_text_truncated(self):
        long_text = "x" * 1000
        result = truncate_text(long_text, 100)
        assert len(result) <= 100 + 20  # +20 for truncation marker
        assert "..." in result

    def test_exact_boundary(self):
        assert truncate_text("hello", 5) == "hello"


class TestSafeFilename:
    def test_normal_name(self):
        assert safe_filename("hello.txt") == "hello.txt"

    def test_special_chars(self):
        name = safe_filename("hello/world:test.txt")
        assert "/" not in name
        assert ":" not in name

    def test_chinese_chars(self):
        name = safe_filename("你好世界.txt")
        assert "你好世界.txt" == name


class TestCurrentTimeStr:
    def test_returns_string(self):
        result = current_time_str("Asia/Shanghai")
        assert isinstance(result, str)
        assert len(result) > 0
```

- [ ] **Step 2: Implement text.py and helpers.py**

```python
# swarm/utils/text.py
"""Text manipulation utilities."""

from __future__ import annotations

from datetime import datetime, timezone


def truncate_text(text: str, max_chars: int) -> str:
    """Truncate text to max_chars, adding ellipsis if truncated."""
    if len(text) <= max_chars:
        return text
    # Keep a bit of context from both ends
    head = text[:max_chars // 2]
    tail = text[-(max_chars // 2):]
    return f"{head}\n... [truncated {len(text) - max_chars:,} chars] ...\n{tail}"


def current_time_str(tz_name: str | None = None) -> str:
    """Return current time as ISO format string."""
    if tz_name:
        try:
            from zoneinfo import ZoneInfo
            tz = ZoneInfo(tz_name)
        except Exception:
            tz = None
    else:
        tz = None
    return datetime.now(tz=tz).strftime("%Y-%m-%d %H:%M:%S %Z")
```

```python
# swarm/utils/helpers.py
"""General-purpose utility functions."""

from __future__ import annotations

import re
from pathlib import Path


def safe_filename(name: str) -> str:
    """Sanitize a string for use as a filename."""
    # Replace path separators and other dangerous chars
    name = re.sub(r'[<>:"/\\|?*]', '_', name)
    # Collapse multiple underscores
    name = re.sub(r'_+', '_', name)
    # Strip leading/trailing dots and spaces
    name = name.strip('. ')
    if not name:
        name = "unnamed"
    return name


def load_bundled_template(relative_path: str) -> str | None:
    """Load a bundled template file from the swarm package."""
    import importlib.resources
    try:
        return importlib.resources.read_text("swarm.templates", relative_path)
    except (FileNotFoundError, ModuleNotFoundError):
        return None
```

```python
# swarm/utils/template.py
"""Jinja2 template rendering utilities."""

from __future__ import annotations

from jinja2 import Environment, BaseLoader


_env = Environment(loader=BaseLoader())


def render_template(template_str: str, **kwargs) -> str:
    """Render a Jinja2 template string with the given variables."""
    template = _env.from_string(template_str)
    return template.render(**kwargs)
```

```python
# swarm/utils/media.py
"""Media (image/audio) format helpers."""

from __future__ import annotations

import mimetypes
from pathlib import Path


def detect_image_mime(data: bytes) -> str | None:
    """Detect image MIME type from magic bytes."""
    if data[:4] == b'\x89PNG':
        return 'image/png'
    if data[:2] == b'\xff\xd8':
        return 'image/jpeg'
    if data[:6] in (b'GIF87a', b'GIF89a'):
        return 'image/gif'
    if data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        return 'image/webp'
    return None


def guess_mime_type(path: str | Path) -> str:
    """Guess MIME type from file extension."""
    mime, _ = mimetypes.guess_type(str(path))
    return mime or "application/octet-stream"


def is_image(path: str | Path) -> bool:
    """Check if a file is an image based on extension."""
    mime = guess_mime_type(path)
    return mime.startswith("image/")


def is_audio(path: str | Path) -> bool:
    """Check if a file is audio based on extension."""
    mime = guess_mime_type(path)
    return mime.startswith("audio/")
```

```python
# swarm/utils/__init__.py
"""Common utilities for Swarm."""
```

- [ ] **Step 3: Run tests**

```bash
pytest tests/test_utils.py -v
```

- [ ] **Step 4: Commit**

```bash
git add swarm/utils/ tests/test_utils.py
git commit -m "feat: add utils module (text, helpers, template, media)"
```

---

### Task 5: Provider Layer

**Files:**
- Create: `swarm/swarm/providers/__init__.py`
- Create: `swarm/swarm/providers/base.py`
- Create: `swarm/swarm/providers/openai_compat.py`
- Create: `swarm/swarm/providers/anthropic.py`
- Create: `swarm/swarm/providers/factory.py`
- Create: `swarm/swarm/providers/retry.py`
- Create: `swarm/swarm/providers/fallback.py`
- Create: `swarm/swarm/providers/token_counter.py`
- Create: `swarm/tests/test_providers.py`

- [ ] **Step 1: Write provider tests**

```python
# tests/test_providers.py
import pytest
from unittest.mock import AsyncMock, patch
from swarm.providers.base import LLMProvider, LLMResponse, StreamChunk
from swarm.providers.openai_compat import OpenAICompatProvider
from swarm.providers.factory import make_provider
from swarm.providers.retry import RetryConfig, async_retry
from swarm.providers.token_counter import TokenCounter


class TestLLMResponse:
    def test_simple_response(self):
        resp = LLMResponse(content="Hello", stop_reason="end_turn")
        assert resp.content == "Hello"
        assert resp.tool_calls == []
        assert not resp.has_tool_calls()

    def test_tool_call_response(self):
        tool_calls = [{"id": "t1", "function": {"name": "search", "arguments": '{"q":"test"}'}}]
        resp = LLMResponse(content=None, stop_reason="tool_calls",
                           tool_calls=tool_calls)
        assert resp.has_tool_calls()
        assert resp.tool_calls == tool_calls


class TestOpenAICompatProvider:
    @pytest.mark.asyncio
    async def test_chat_basic(self):
        provider = OpenAICompatProvider(
            api_key="sk-test",
            base_url="https://api.openai.com/v1",
            model="gpt-4o",
        )
        mock_response = {
            "choices": [{"message": {"content": "Hi!", "tool_calls": None},
                         "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5}
        }
        with patch.object(provider._client.chat.completions, 'create',
                          AsyncMock(return_value=mock_response)):
            resp = await provider.chat(messages=[{"role": "user", "content": "hello"}])
            assert resp.content == "Hi!"
            assert resp.stop_reason == "end_turn"

    @pytest.mark.asyncio
    async def test_stream_basic(self):
        provider = OpenAICompatProvider(
            api_key="sk-test",
            base_url="https://api.openai.com/v1",
            model="gpt-4o",
        )
        chunks = [
            type('obj', (object,), {
                'choices': [type('obj', (object,), {
                    'delta': type('obj', (object,), {'content': 'Hello'})(),
                    'finish_reason': None
                })()]
            })(),
            type('obj', (object,), {
                'choices': [type('obj', (object,), {
                    'delta': type('obj', (object,), {'content': ' world'})(),
                    'finish_reason': 'stop'
                })()]
            })(),
        ]
        with patch.object(provider._client.chat.completions, 'create',
                          return_value=chunks):
            collected = []
            async for chunk in provider.stream(messages=[{"role": "user", "content": "hi"}]):
                collected.append(chunk)
            assert len(collected) == 2
            assert collected[0].content == "Hello"


class TestRetry:
    @pytest.mark.asyncio
    async def test_successful_call_no_retry(self):
        call_count = 0

        @async_retry(RetryConfig(max_retries=3, base_delay=0.01))
        async def succeed():
            nonlocal call_count
            call_count += 1
            return "ok"

        result = await succeed()
        assert result == "ok"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_retry_on_exception(self):
        call_count = 0

        @async_retry(RetryConfig(max_retries=3, base_delay=0.01))
        async def fail_then_succeed():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("temporary")
            return "recovered"

        result = await fail_then_succeed()
        assert result == "recovered"
        assert call_count == 3


class TestTokenCounter:
    def test_estimate_simple(self):
        counter = TokenCounter()
        tokens = counter.estimate("Hello world, this is a test.")
        assert tokens > 0

    def test_estimate_empty(self):
        counter = TokenCounter()
        assert counter.estimate("") == 0

    def test_estimate_messages(self):
        counter = TokenCounter()
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hi there!"},
        ]
        tokens = counter.estimate_messages(messages)
        assert tokens > 10
```

- [ ] **Step 2: Implement providers/base.py**

```python
"""Abstract LLM provider interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, AsyncIterator


@dataclass
class StreamChunk:
    """A single chunk from a streaming response."""
    content: str | None = None
    tool_call_delta: dict | None = None
    finish_reason: str | None = None
    usage: dict | None = None
    reasoning_content: str | None = None


@dataclass
class LLMResponse:
    """Complete LLM response after streaming or non-streaming call."""
    content: str | None
    stop_reason: str  # "end_turn", "tool_calls", "max_tokens", "error"
    tool_calls: list[dict] = field(default_factory=list)
    usage: dict = field(default_factory=dict)
    reasoning_content: str | None = None

    def has_tool_calls(self) -> bool:
        return len(self.tool_calls) > 0


class LLMProvider(ABC):
    """Abstract base for LLM providers."""

    def __init__(self, api_key: str, model: str, **kwargs):
        self.api_key = api_key
        self.model = model
        self.generation = type('obj', (object,), {'max_tokens': kwargs.get('max_tokens', 4096)})()

    @abstractmethod
    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        **kwargs,
    ) -> LLMResponse:
        """Send messages and get a complete response."""
        ...

    @abstractmethod
    async def stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        **kwargs,
    ) -> AsyncIterator[StreamChunk]:
        """Stream response chunks."""
        ...

    def count_tokens(self, text: str) -> int:
        """Estimate token count for a text string."""
        return len(text) // 4  # Rough estimate (~4 chars per token)

    def get_default_model(self) -> str:
        return self.model

    @property
    def context_window(self) -> int:
        return 128_000  # Default for GPT-4o
```

- [ ] **Step 3: Implement providers/retry.py**

```python
"""Retry logic for LLM API calls."""

from __future__ import annotations

import asyncio
import functools
import random
from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class RetryConfig:
    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    jitter: bool = True


def async_retry(config: RetryConfig | None = None):
    """Decorator for async functions: retry on exception with exponential backoff."""
    if config is None:
        config = RetryConfig()

    def decorator(func: Callable):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(config.max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt == config.max_retries:
                        raise
                    delay = min(
                        config.base_delay * (2 ** attempt),
                        config.max_delay,
                    )
                    if config.jitter:
                        delay *= 0.5 + random.random()
                    await asyncio.sleep(delay)
            raise last_exception  # type: ignore
        return wrapper
    return decorator
```

- [ ] **Step 4: Implement providers/openai_compat.py**

```python
"""OpenAI-compatible provider (works with vLLM, Ollama, etc.)."""

from __future__ import annotations

from typing import Any, AsyncIterator

from openai import AsyncOpenAI

from swarm.providers.base import LLMProvider, LLMResponse, StreamChunk
from swarm.providers.retry import RetryConfig, async_retry


class OpenAICompatProvider(LLMProvider):
    """Provider for OpenAI and OpenAI-compatible APIs."""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.openai.com/v1",
        model: str = "gpt-4o",
        max_tokens: int = 4096,
        temperature: float = 0.7,
        **kwargs,
    ):
        super().__init__(api_key=api_key, model=model, max_tokens=max_tokens)
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._retry_config = RetryConfig(max_retries=3)

    @async_retry(RetryConfig(max_retries=3))
    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        **kwargs,
    ) -> LLMResponse:
        kwargs.setdefault("temperature", self._temperature)
        kwargs.setdefault("max_tokens", self._max_tokens)

        response = await self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=tools or None,
            **kwargs,
        )

        choice = response.choices[0]
        usage = response.usage.model_dump() if response.usage else {}

        if choice.finish_reason == "tool_calls" or choice.message.tool_calls:
            return LLMResponse(
                content=choice.message.content,
                stop_reason="tool_calls",
                tool_calls=[
                    {
                        "id": tc.id,
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in (choice.message.tool_calls or [])
                ],
                usage=usage,
            )

        return LLMResponse(
            content=choice.message.content,
            stop_reason="end_turn",
            usage=usage,
        )

    async def stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        **kwargs,
    ) -> AsyncIterator[StreamChunk]:
        kwargs.setdefault("temperature", self._temperature)
        kwargs.setdefault("max_tokens", self._max_tokens)

        stream = await self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=tools or None,
            stream=True,
            **kwargs,
        )

        async for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta is None:
                continue

            yield StreamChunk(
                content=delta.content,
                finish_reason=chunk.choices[0].finish_reason if chunk.choices else None,
            )

    @property
    def context_window(self) -> int:
        # Known context windows
        windows = {
            "gpt-4o": 128_000,
            "gpt-4o-mini": 128_000,
            "gpt-4-turbo": 128_000,
            "gpt-3.5-turbo": 16_384,
        }
        return windows.get(self.model, 128_000)
```

- [ ] **Step 5: Implement remaining provider modules**

```python
# swarm/providers/factory.py
"""Provider factory: create LLMProvider from configuration."""

from __future__ import annotations

from swarm.config.schema import LLMConfig
from swarm.providers.base import LLMProvider
from swarm.providers.openai_compat import OpenAICompatProvider


def make_provider(config: LLMConfig) -> LLMProvider:
    """Create a provider instance from configuration."""
    provider_type = config.provider

    if provider_type in ("openai", "custom"):
        return OpenAICompatProvider(
            api_key=config.api_key,
            base_url=config.base_url,
            model=config.model,
            max_tokens=config.max_tokens,
            temperature=config.temperature,
        )
    elif provider_type == "anthropic":
        from swarm.providers.anthropic import AnthropicProvider
        return AnthropicProvider(
            api_key=config.api_key,
            model=config.model,
            max_tokens=config.max_tokens,
            temperature=config.temperature,
        )
    else:
        raise ValueError(f"Unknown provider type: {provider_type}")
```

```python
# swarm/providers/token_counter.py
"""Token counting: tiktoken-based exact count with estimation fallback."""

from __future__ import annotations

from typing import Any


class TokenCounter:
    """Token counter using tiktoken when available, estimation otherwise."""

    def __init__(self, model: str = "gpt-4o"):
        self.model = model
        self._encoder = None
        try:
            import tiktoken
            if "gpt-4" in model or "gpt-3.5" in model:
                self._encoder = tiktoken.get_encoding("cl100k_base")
            elif "claude" in model:
                self._encoder = None  # Anthropic uses different tokenizer
        except ImportError:
            pass

    def count(self, text: str) -> int:
        """Count tokens in text."""
        if self._encoder:
            return len(self._encoder.encode(text))
        return self.estimate(text)

    def estimate(self, text: str) -> int:
        """Rough token estimate: ~4 characters per token."""
        if not text:
            return 0
        return max(1, len(text) // 4)

    def estimate_messages(self, messages: list[dict[str, Any]]) -> int:
        """Estimate total tokens for a list of messages."""
        total = 0
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                total += self.estimate(content)
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        total += self.estimate(block.get("text", ""))
            total += 4  # message framing overhead
        return total
```

```python
# swarm/providers/fallback.py
"""Fallback provider chain: try primary, fall through to backups on failure."""

from __future__ import annotations

from typing import Any

from swarm.providers.base import LLMProvider, LLMResponse


class FallbackProvider(LLMProvider):
    """Composite provider that falls back through a chain on failure."""

    def __init__(self, providers: list[LLMProvider]):
        self._providers = providers
        super().__init__(api_key="", model=providers[0].model if providers else "")

    async def chat(self, messages, tools=None, **kwargs) -> LLMResponse:
        last_error = None
        for i, provider in enumerate(self._providers):
            try:
                return await provider.chat(messages, tools=tools, **kwargs)
            except Exception as e:
                last_error = e
                if i < len(self._providers) - 1:
                    from structlog import get_logger
                    get_logger().warning(
                        "Provider fallback",
                        from_provider=type(provider).__name__,
                        to_provider=type(self._providers[i + 1]).__name__,
                        error=str(e),
                    )
        raise last_error or RuntimeError("All providers failed")

    async def stream(self, messages, tools=None, **kwargs):
        # Streaming fallback: try primary, fall through on first chunk failure
        for i, provider in enumerate(self._providers):
            try:
                async for chunk in provider.stream(messages, tools=tools, **kwargs):
                    yield chunk
                return
            except Exception as e:
                if i == len(self._providers) - 1:
                    raise
```

```python
# swarm/providers/anthropic.py
"""Anthropic provider using the native Messages API."""

from __future__ import annotations

from typing import Any, AsyncIterator

from swarm.providers.base import LLMProvider, LLMResponse, StreamChunk
from swarm.providers.retry import RetryConfig, async_retry


class AnthropicProvider(LLMProvider):
    """Provider for Anthropic Claude models."""

    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-4-6",
        max_tokens: int = 4096,
        temperature: float = 0.7,
        **kwargs,
    ):
        super().__init__(api_key=api_key, model=model, max_tokens=max_tokens)
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._client = None  # Lazy-init

    def _get_client(self):
        if self._client is None:
            from anthropic import AsyncAnthropic
            self._client = AsyncAnthropic(api_key=self.api_key)
        return self._client

    @async_retry(RetryConfig(max_retries=3))
    async def chat(self, messages, tools=None, **kwargs) -> LLMResponse:
        client = self._get_client()
        # Convert OpenAI-format messages/tools to Anthropic format
        system_prompt = ""
        anthropic_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system_prompt = msg["content"] if isinstance(msg["content"], str) else ""
            elif msg["role"] == "user":
                anthropic_messages.append({"role": "user", "content": msg["content"]})
            elif msg["role"] == "assistant":
                anthropic_messages.append({"role": "assistant", "content": msg.get("content", "") or ""})

        anthropic_tools = None
        if tools:
            anthropic_tools = [
                {
                    "name": t["function"]["name"],
                    "description": t["function"].get("description", ""),
                    "input_schema": t["function"].get("parameters", {"type": "object"}),
                }
                for t in tools
            ]

        kwargs.pop("temperature", None)
        kwargs.pop("max_tokens", None)
        response = await client.messages.create(
            model=self.model,
            system=system_prompt if system_prompt else "You are a helpful assistant.",
            messages=anthropic_messages,
            tools=anthropic_tools,
            max_tokens=self._max_tokens,
            **kwargs,
        )

        # Convert back to standard format
        tool_calls = []
        text_content = ""
        for block in response.content:
            if block.type == "text":
                text_content += block.text
            elif block.type == "tool_use":
                tool_calls.append({
                    "id": block.id,
                    "function": {
                        "name": block.name,
                        "arguments": block.input if isinstance(block.input, str) else str(block.input),
                    },
                })

        return LLMResponse(
            content=text_content or None,
            stop_reason="tool_calls" if tool_calls else "end_turn",
            tool_calls=tool_calls,
            usage=response.usage.model_dump() if response.usage else {},
        )

    async def stream(self, messages, tools=None, **kwargs) -> AsyncIterator[StreamChunk]:
        # For simplicity, non-streaming fallback for Anthropic
        response = await self.chat(messages, tools=tools, **kwargs)
        if response.content:
            yield StreamChunk(content=response.content, finish_reason=response.stop_reason)
```

```python
# swarm/providers/__init__.py
"""LLM provider layer — OpenAI, Anthropic, fallback, retry, token counting."""

from swarm.providers.base import LLMProvider, LLMResponse, StreamChunk
from swarm.providers.factory import make_provider
from swarm.providers.fallback import FallbackProvider

__all__ = [
    "LLMProvider",
    "LLMResponse",
    "StreamChunk",
    "make_provider",
    "FallbackProvider",
]
```

- [ ] **Step 7: Run tests**

```bash
pytest tests/test_providers.py -v
```

- [ ] **Step 8: Commit**

```bash
git add swarm/providers/ tests/test_providers.py
git commit -m "feat: add provider layer (OpenAI, Anthropic, fallback, retry, token counting)"
```

---

### Task 6: Agent Core — Context

**Files:**
- Create: `swarm/swarm/agent/__init__.py`
- Create: `swarm/swarm/agent/context.py`

- [ ] **Step 1: Write context tests**

```python
# tests/test_agent_context.py
import pytest
from swarm.agent.context import RequestContext


class TestRequestContext:
    def test_immutable(self):
        ctx = RequestContext(
            trace_id="t1",
            chat_id="chat_A",
            chat_type="p2p",
            user_id="user_1",
            message_id="msg_1",
        )
        with pytest.raises(Exception):
            ctx.chat_id = "chat_B"  # frozen dataclass

    def test_minimal_construction(self):
        ctx = RequestContext(
            trace_id="t1",
            chat_id="chat_A",
            chat_type="p2p",
            user_id="u1",
            message_id="m1",
        )
        assert ctx.user_token is None
        assert ctx.permissions == frozenset()

    def test_with_token(self):
        ctx = RequestContext(
            trace_id="t1",
            chat_id="chat_A",
            chat_type="p2p",
            user_id="u1",
            message_id="m1",
            user_token="tok_xxx",
        )
        assert ctx.user_token == "tok_xxx"
```

- [ ] **Step 2: Implement agent/context.py**

```python
"""RequestContext — immutable per-request isolation core."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import FrozenSet


@dataclass(frozen=True)
class RequestContext:
    """Immutable per-request context.

    Passed explicitly to ALL stateful functions.
    Framework code MUST NOT use os.environ or contextvars for per-request state.
    """

    trace_id: str              # UUID — traces request through all subsystems
    chat_id: str               # Tenant key — root of all isolation
    chat_type: str             # "p2p" | "group"
    user_id: str               # Feishu open_id
    message_id: str            # Feishu message_id (idempotency)
    user_token: str | None = None       # user_access_token
    permissions: frozenset[str] = field(default_factory=frozenset)
    locale: str = "zh-CN"


@dataclass
class TurnContext:
    """Mutable turn-level state — only used within a single turn, not persisted."""
    ctx: RequestContext
    messages: list[dict] = field(default_factory=list)
    tools_used: list[str] = field(default_factory=list)
    final_content: str | None = None
    stop_reason: str = ""
```

- [ ] **Step 3: Run tests and commit**

```bash
pytest tests/test_agent_context.py -v
git add swarm/agent/ tests/test_agent_context.py
git commit -m "feat: add RequestContext — immutable per-request isolation core"
```

---

### Task 7: Agent Core — Runner

**Files:**
- Create: `swarm/swarm/agent/runner.py`

- [ ] **Step 1: Write runner tests**

```python
# tests/test_agent_runner.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from swarm.agent.context import RequestContext
from swarm.agent.runner import AgentRunner, AgentRunSpec


@pytest.fixture
def sample_ctx():
    return RequestContext(
        trace_id="t1", chat_id="c1", chat_type="p2p",
        user_id="u1", message_id="m1",
    )


class TestAgentRunner:
    @pytest.mark.asyncio
    async def test_simple_response(self, sample_ctx):
        provider = MagicMock()
        provider.chat = AsyncMock(return_value=MagicMock(
            content="Hello!", stop_reason="end_turn",
            tool_calls=[], usage={}, has_tool_calls=lambda: False,
        ))

        runner = AgentRunner(provider)
        spec = AgentRunSpec(
            initial_messages=[{"role": "user", "content": "hi"}],
            model="gpt-4o",
        )
        result = await runner.run(spec)

        assert result.final_content == "Hello!"
        assert result.stop_reason == "end_turn"

    @pytest.mark.asyncio
    async def test_tool_call_loop(self, sample_ctx):
        provider = MagicMock()
        # First call returns tool call
        provider.chat = AsyncMock(side_effect=[
            MagicMock(content=None, stop_reason="tool_calls",
                      tool_calls=[{"id": "t1", "function": {"name": "echo", "arguments": '{"text":"hi"}'}}],
                      usage={}, has_tool_calls=lambda: True),
            MagicMock(content="Done!", stop_reason="end_turn",
                      tool_calls=[], usage={}, has_tool_calls=lambda: False),
        ])

        # Mock tool registry
        tools = MagicMock()
        tools.get_definitions.return_value = []
        tools.execute = AsyncMock(return_value="echo: hi")

        runner = AgentRunner(provider)
        spec = AgentRunSpec(
            initial_messages=[{"role": "user", "content": "echo hi"}],
            tools=tools,
            model="gpt-4o",
        )
        result = await runner.run(spec)

        assert result.final_content == "Done!"
        assert "echo" in result.tools_used
```

- [ ] **Step 2: Implement agent/runner.py**

```python
"""AgentRunner — LLM call + tool execution loop."""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable

import structlog

from swarm.agent.context import RequestContext
from swarm.providers.base import LLMProvider

logger = structlog.get_logger(__name__)


@dataclass
class AgentRunSpec:
    """Specification for a single agent run."""
    initial_messages: list[dict[str, Any]]
    tools: Any | None = None         # ToolRegistry
    model: str = "gpt-4o"
    max_iterations: int = 30
    max_tool_result_chars: int = 16_000
    hook: Any | None = None          # AgentHook
    error_message: str = "Sorry, an error occurred."
    concurrent_tools: bool = False
    workspace: str = "."
    session_key: str | None = None
    context_window_tokens: int = 128_000
    context_block_limit: int | None = None
    provider_retry_mode: str = "standard"
    progress_callback: Callable | None = None
    stream_progress_deltas: bool = False
    retry_wait_callback: Callable | None = None
    checkpoint_callback: Callable | None = None
    injection_callback: Callable | None = None
    llm_timeout_s: float = 120.0
    goal_active_predicate: Callable | None = None
    goal_continue_message: str = ""


@dataclass
class AgentRunResult:
    """Result from a completed agent run."""
    final_content: str | None
    tools_used: list[str] = field(default_factory=list)
    messages: list[dict[str, Any]] = field(default_factory=list)
    stop_reason: str = ""
    had_injections: bool = False
    usage: dict[str, int] = field(default_factory=dict)


class AgentRunner:
    """Executes the LLM conversation loop with tool execution."""

    def __init__(self, provider: LLMProvider):
        self.provider = provider

    async def run(self, spec: AgentRunSpec) -> AgentRunResult:
        """Execute one complete agent turn."""
        messages = list(spec.initial_messages)
        tools_used: list[str] = []
        total_usage: dict[str, int] = {}
        stop_reason = "end_turn"
        had_injections = False

        for iteration in range(spec.max_iterations):
            # Check for mid-turn injections
            if spec.injection_callback:
                injected = await spec.injection_callback(limit=3)
                if injected:
                    messages.extend(injected)
                    had_injections = True

            # Build tool definitions
            tool_defs = None
            if spec.tools:
                tool_defs = spec.tools.get_definitions()

            # Call LLM
            try:
                response = await asyncio.wait_for(
                    self.provider.chat(messages, tools=tool_defs),
                    timeout=spec.llm_timeout_s,
                )
            except asyncio.TimeoutError:
                logger.error("LLM call timed out")
                stop_reason = "error"
                return AgentRunResult(
                    final_content="Sorry, the request timed out.",
                    stop_reason=stop_reason,
                    usage=total_usage,
                )
            except Exception as e:
                logger.error("LLM call failed", error=str(e))
                stop_reason = "error"
                return AgentRunResult(
                    final_content=spec.error_message,
                    stop_reason=stop_reason,
                    usage=total_usage,
                )

            # Accumulate usage
            if response.usage:
                for k, v in response.usage.items():
                    total_usage[k] = total_usage.get(k, 0) + (v or 0)

            # Process tool calls
            if response.has_tool_calls():
                # Persist checkpoint before tool execution
                if spec.checkpoint_callback:
                    await spec.checkpoint_callback({
                        "assistant_message": {
                            "role": "assistant",
                            "content": response.content,
                            "tool_calls": response.tool_calls,
                        },
                        "completed_tool_results": [],
                        "pending_tool_calls": response.tool_calls,
                    })

                # Add assistant message with tool calls
                assistant_msg = {
                    "role": "assistant",
                    "content": response.content,
                    "tool_calls": response.tool_calls,
                }
                messages.append(assistant_msg)

                # Execute tools
                completed_results = []
                for tc in response.tool_calls:
                    name = tc["function"]["name"]
                    try:
                        args = json.loads(tc["function"]["arguments"])
                    except json.JSONDecodeError:
                        args = {}

                    tools_used.append(name)

                    try:
                        result = await asyncio.wait_for(
                            spec.tools.execute(name, args),
                            timeout=60.0,
                        )
                    except asyncio.TimeoutError:
                        result = f"Error: tool '{name}' timed out"
                    except Exception as e:
                        result = f"Error executing '{name}': {e}"

                    # Truncate long results
                    if isinstance(result, str) and len(result) > spec.max_tool_result_chars:
                        result = result[:spec.max_tool_result_chars] + "\n... [truncated]"

                    tool_msg = {
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "name": name,
                        "content": result,
                    }
                    messages.append(tool_msg)
                    completed_results.append(tool_msg)

                # Update checkpoint
                if spec.checkpoint_callback:
                    await spec.checkpoint_callback({
                        "assistant_message": assistant_msg,
                        "completed_tool_results": completed_results,
                        "pending_tool_calls": [],
                    })

                continue  # Go back for next LLM call

            # No tool calls — final response
            messages.append({"role": "assistant", "content": response.content})
            stop_reason = response.stop_reason
            return AgentRunResult(
                final_content=response.content,
                tools_used=tools_used,
                messages=messages,
                stop_reason=stop_reason,
                had_injections=had_injections,
                usage=total_usage,
            )

        # Max iterations reached
        logger.warning("Max iterations reached", max_iterations=spec.max_iterations)
        return AgentRunResult(
            final_content=None,
            tools_used=tools_used,
            messages=messages,
            stop_reason="max_iterations",
            had_injections=had_injections,
            usage=total_usage,
        )
```

- [ ] **Step 3: Run tests and commit**

```bash
pytest tests/test_agent_runner.py -v
git add swarm/agent/runner.py tests/test_agent_runner.py
git commit -m "feat: add AgentRunner — LLM call + tool execution loop"
```

---

---

### Task 8: AgentLoop — The Core Orchestrator

**Files:**
- Create: `swarm/swarm/agent/loop.py`
- Create: `swarm/tests/test_agent_loop.py`

- [ ] **Step 1: Write AgentLoop tests**

```python
# tests/test_agent_loop.py
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from swarm.agent.context import RequestContext
from swarm.agent.loop import AgentLoop, TurnState
from swarm.bus.queue import MessageBus, InboundMessage
from swarm.providers.base import LLMResponse


@pytest.fixture
def bus():
    return MessageBus()


@pytest.fixture
def mock_provider():
    p = MagicMock()
    p.chat = AsyncMock(return_value=LLMResponse(content="Hello!", stop_reason="end_turn"))
    p.model = "gpt-4o"
    p.context_window = 128_000
    p.generation = MagicMock()
    p.generation.max_tokens = 4096
    return p


@pytest.fixture
def loop(bus, mock_provider):
    return AgentLoop(
        bus=bus,
        provider=mock_provider,
        workspace=".",
    )


class TestTurnStateMachine:
    def test_transitions(self):
        """Verify all defined transitions are valid."""
        transitions = AgentLoop._TRANSITIONS
        assert (TurnState.RESTORE, "ok") in transitions
        assert (TurnState.BUILD, "ok") in transitions
        assert (TurnState.BUILD, "cmd") in transitions
        assert (TurnState.RUN, "ok") in transitions
        assert (TurnState.SAVE, "ok") in transitions
        assert (TurnState.RESPOND, "ok") in transitions

    def test_all_states_covered(self):
        """Every state except DONE should have at least one outgoing transition."""
        transitions = AgentLoop._TRANSITIONS
        sources = {t[0] for t in transitions}
        assert TurnState.RESTORE in sources
        assert TurnState.BUILD in sources
        assert TurnState.RUN in sources
        assert TurnState.SAVE in sources
        assert TurnState.RESPOND in sources


class TestAgentLoopProcessing:
    @pytest.mark.asyncio
    async def test_process_direct_simple(self, loop, mock_provider):
        """Direct message processing returns a response."""
        mock_provider.chat = AsyncMock(return_value=LLMResponse(
            content="Hi there!", stop_reason="end_turn"))

        result = await loop.process_direct("hello", session_key="test:direct")
        assert result is not None
        assert "Hi there!" in result.content

    @pytest.mark.asyncio
    async def test_command_shortcut(self, loop, mock_provider):
        """Slash commands skip LLM call."""
        result = await loop.process_direct("/help", session_key="test:direct")
        assert result is not None
        # /help should generate a response without calling LLM
        # Verify LLM was NOT called for a built-in command
        assert mock_provider.chat.call_count == 0

    @pytest.mark.asyncio
    async def test_concurrent_different_sessions(self, loop, mock_provider):
        """Different chat_ids process concurrently."""
        mock_provider.chat = AsyncMock(side_effect=[
            LLMResponse(content="Response A", stop_reason="end_turn"),
            LLMResponse(content="Response B", stop_reason="end_turn"),
        ])
        results = await asyncio.gather(
            loop.process_direct("hello A", session_key="test:A"),
            loop.process_direct("hello B", session_key="test:B"),
        )
        assert len(results) == 2
        contents = {r.content for r in results}
        assert "Response A" in contents
        assert "Response B" in contents

    @pytest.mark.asyncio
    async def test_same_session_serialized(self, loop, mock_provider):
        """Same chat_id messages are processed serially."""
        order = []

        async def side_effect(messages, tools=None, **kw):
            await asyncio.sleep(0.01)
            order.append("called")
            return LLMResponse(content="OK", stop_reason="end_turn")

        mock_provider.chat = AsyncMock(side_effect=side_effect)

        await asyncio.gather(
            loop.process_direct("msg 1", session_key="test:serial"),
            loop.process_direct("msg 2", session_key="test:serial"),
        )
        assert len(order) == 2
```

- [ ] **Step 2: Run tests — expect failure**

```bash
pytest tests/test_agent_loop.py -v
```

Expected: ImportError — `AgentLoop` not defined yet.

- [ ] **Step 3: Implement agent/loop.py**

```python
"""AgentLoop — the core state machine orchestrator."""

from __future__ import annotations

import asyncio
import time
import uuid
from contextlib import nullcontext, suppress
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Any, Callable

import structlog

from swarm.agent.context import RequestContext, TurnContext
from swarm.agent.runner import AgentRunner, AgentRunSpec, AgentRunResult
from swarm.bus.queue import InboundMessage, MessageBus, OutboundMessage
from swarm.providers.base import LLMProvider

logger = structlog.get_logger(__name__)


class TurnState(Enum):
    RESTORE = auto()
    BUILD = auto()
    RUN = auto()
    SAVE = auto()
    RESPOND = auto()
    DONE = auto()


@dataclass
class StateTraceEntry:
    state: TurnState
    started_at: float
    duration_ms: float
    event: str
    error: str | None = None


class AgentLoop:
    """Core agent processing engine with a 5-state machine.

    States: RESTORE → BUILD → RUN → SAVE → RESPOND → DONE
    Commands (like /help) shortcut from BUILD → RESPOND, skipping LLM.

    Key properties:
    - Per-session asyncio.Lock for serial execution per chat_id
    - Global semaphore for concurrency limiting
    - Mid-turn message injection via pending queues
    - Checkpoint persistence for crash recovery
    """

    _TRANSITIONS: dict[tuple[TurnState, str], TurnState] = {
        (TurnState.RESTORE, "ok"):   TurnState.BUILD,
        (TurnState.BUILD,   "ok"):   TurnState.RUN,
        (TurnState.BUILD,   "cmd"):  TurnState.RESPOND,
        (TurnState.RUN,     "ok"):   TurnState.SAVE,
        (TurnState.SAVE,    "ok"):   TurnState.RESPOND,
        (TurnState.RESPOND, "ok"):   TurnState.DONE,
    }

    _MAX_CONCURRENT = 10
    _PENDING_QUEUE_SIZE = 20

    def __init__(
        self,
        bus: MessageBus,
        provider: LLMProvider,
        workspace: str | Path = ".",
        model: str | None = None,
        max_iterations: int = 30,
        max_tool_result_chars: int = 16_000,
        tools: Any = None,
        sessions: Any = None,
        memory: Any = None,
        context: Any = None,
    ):
        self.bus = bus
        self.provider = provider
        self.workspace = Path(workspace)
        self.model = model or provider.model
        self.max_iterations = max_iterations
        self.max_tool_result_chars = max_tool_result_chars
        self.tools = tools
        self.sessions = sessions
        self.memory = memory
        self.context_builder = context

        self.runner = AgentRunner(provider)
        self._running = False
        self._session_locks: dict[str, asyncio.Lock] = {}
        self._active_tasks: dict[str, list[asyncio.Task]] = {}
        self._pending_queues: dict[str, asyncio.Queue] = {}
        self._concurrency_gate = asyncio.Semaphore(self._MAX_CONCURRENT)
        self._commands: dict[str, Callable] = {}
        self._register_default_commands()

    def _register_default_commands(self) -> None:
        """Register built-in slash commands."""
        self._commands["/help"] = self._cmd_help
        self._commands["/status"] = self._cmd_status
        self._commands["/clear"] = self._cmd_clear

    async def _cmd_help(self, ctx: RequestContext) -> str:
        return """**Swarm Commands**
- `/help` — Show this help
- `/status` — Show session status
- `/clear` — Clear conversation history
- `/exit` — (CLI only) Exit chat mode"""

    async def _cmd_status(self, ctx: RequestContext) -> str:
        active = len(self._active_tasks)
        return f"**Status**\n- Active sessions: {active}\n- Model: {self.model}\n- Chat ID: {ctx.chat_id}"

    async def _cmd_clear(self, ctx: RequestContext) -> str:
        if self.sessions:
            key = f"feishu:{ctx.chat_id}"
            self.sessions.clear(key)
            return "Conversation history cleared."
        return "Session manager not available."

    def _is_command(self, text: str) -> str | None:
        """Check if text is a registered command. Returns command key or None."""
        stripped = text.strip().lower()
        for cmd in self._commands:
            if stripped.startswith(cmd):
                return cmd
        return None

    async def _process_message(
        self,
        msg: InboundMessage,
        session_key: str,
    ) -> OutboundMessage | None:
        """Run a single message through the 5-state machine."""
        trace_id = str(uuid.uuid4())
        ctx = RequestContext(
            trace_id=trace_id,
            chat_id=msg.chat_id,
            chat_type=msg.metadata.get("chat_type", "p2p"),
            user_id=msg.sender_id,
            message_id=msg.metadata.get("message_id", ""),
        )

        turn = TurnContext(ctx=ctx)
        state = TurnState.RESTORE
        history: list[dict] = []

        while state is not TurnState.DONE:
            t0 = time.perf_counter()

            if state == TurnState.RESTORE:
                # Restore session state
                if self.sessions:
                    session = self.sessions.get_or_create(msg.session_key)
                    history = session.get_history(max_messages=50)
                event = "ok"

            elif state == TurnState.BUILD:
                # Check for command shortcut
                cmd = self._is_command(msg.content)
                if cmd:
                    handler = self._commands[cmd]
                    turn.final_content = await handler(ctx)
                    turn.stop_reason = "command"
                    event = "cmd"
                else:
                    # Build messages for LLM
                    turn.messages = [{"role": "system", "content": "You are a helpful assistant named Swarm."}]
                    if history:
                        turn.messages.extend(history)
                    turn.messages.append({"role": "user", "content": msg.content})
                    event = "ok"

            elif state == TurnState.RUN:
                spec = AgentRunSpec(
                    initial_messages=turn.messages,
                    tools=self.tools,
                    model=self.model,
                    max_iterations=self.max_iterations,
                    max_tool_result_chars=self.max_tool_result_chars,
                )
                result = await self.runner.run(spec)
                turn.final_content = result.final_content or ""
                turn.tools_used = result.tools_used
                turn.stop_reason = result.stop_reason
                event = "ok"

            elif state == TurnState.SAVE:
                if self.sessions and turn.final_content:
                    session = self.sessions.get_or_create(msg.session_key)
                    session.add_message("user", msg.content)
                    session.add_message("assistant", turn.final_content)
                    self.sessions.save(session)
                event = "ok"

            elif state == TurnState.RESPOND:
                return OutboundMessage(
                    channel=msg.channel,
                    chat_id=msg.chat_id,
                    content=turn.final_content or "",
                    metadata={"trace_id": trace_id, "stop_reason": turn.stop_reason},
                )
                # event = "ok" not needed — we return directly

            duration = (time.perf_counter() - t0) * 1000
            logger.debug("State transition",
                         state=state.name, event=event, duration_ms=round(duration, 1),
                         trace_id=trace_id)

            next_state = self._TRANSITIONS.get((state, event))
            if next_state is None:
                logger.error("No transition from state on event",
                            state=state.name, event=event)
                return OutboundMessage(
                    channel=msg.channel,
                    chat_id=msg.chat_id,
                    content="Sorry, an internal error occurred.",
                )
            state = next_state

        return None

    async def _dispatch(self, msg: InboundMessage) -> None:
        """Dispatch a message with per-session serialization."""
        session_key = msg.session_key
        lock = self._session_locks.setdefault(session_key, asyncio.Lock())
        gate = self._concurrency_gate or nullcontext()

        async with lock, gate:
            try:
                response = await self._process_message(msg, session_key)
                if response:
                    await self.bus.publish_outbound(response)
            except asyncio.CancelledError:
                logger.info("Task cancelled for session", session_key=session_key)
                raise
            except Exception:
                logger.exception("Error processing message", session_key=session_key)
                await self.bus.publish_outbound(OutboundMessage(
                    channel=msg.channel,
                    chat_id=msg.chat_id,
                    content="Sorry, I encountered an error processing your message.",
                ))

    async def run(self) -> None:
        """Main event loop: consume from bus, dispatch as tasks."""
        self._running = True
        logger.info("AgentLoop started")

        while self._running:
            try:
                msg = await asyncio.wait_for(self.bus.consume_inbound(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                if asyncio.current_task().cancelling():
                    raise
                continue

            task = asyncio.create_task(self._dispatch(msg))
            session_key = msg.session_key
            self._active_tasks.setdefault(session_key, []).append(task)
            task.add_done_callback(
                lambda t, k=session_key: (
                    self._active_tasks.get(k, []) and
                    self._active_tasks[k].remove(t)
                    if t in self._active_tasks.get(k, [])
                    else None
                )
            )

    def stop(self) -> None:
        """Signal the AgentLoop to stop accepting new messages."""
        self._running = False
        self.bus.stop_accepting()
        logger.info("AgentLoop stopping")

    async def shutdown(self, timeout: float = 30.0) -> None:
        """Graceful shutdown: drain in-flight turns, then stop."""
        self.stop()
        # Wait for active tasks to finish
        all_tasks = [t for tasks in self._active_tasks.values() for t in tasks if not t.done()]
        if all_tasks:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*all_tasks, return_exceptions=True),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                logger.warning("Shutdown timeout, cancelling remaining tasks")
                for t in all_tasks:
                    t.cancel()

    async def process_direct(
        self,
        content: str,
        session_key: str = "cli:direct",
        channel: str = "cli",
        chat_id: str = "direct",
    ) -> OutboundMessage | None:
        """Process a message directly (used by CLI)."""
        msg = InboundMessage(
            channel=channel,
            sender_id="user",
            chat_id=chat_id,
            content=content,
            session_key_override=session_key,
        )
        lock = self._session_locks.setdefault(session_key, asyncio.Lock())
        async with lock:
            return await self._process_message(msg, session_key)
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_agent_loop.py -v
```

- [ ] **Step 5: Commit**

```bash
git add swarm/agent/loop.py tests/test_agent_loop.py
git commit -m "feat: add AgentLoop — 5-state core orchestrator"
```

---

### Task 9: Session Manager

**Files:**
- Create: `swarm/swarm/session/__init__.py`
- Create: `swarm/swarm/session/manager.py`
- Create: `swarm/swarm/session/goal_state.py`
- Create: `swarm/swarm/session/continuation.py`
- Create: `swarm/tests/test_session.py`

- [ ] **Step 1: Write session tests**

```python
# tests/test_session.py
import pytest
import tempfile
from pathlib import Path
from swarm.session.manager import Session, SessionManager


class TestSession:
    def test_add_message(self):
        s = Session(key="test:chat_A")
        s.add_message("user", "hello")
        s.add_message("assistant", "hi there")
        assert len(s.messages) == 2
        assert s.messages[0]["role"] == "user"
        assert s.messages[1]["role"] == "assistant"

    def test_get_history(self):
        s = Session(key="test:chat_A")
        for i in range(50):
            s.add_message("user", f"msg {i}")
        history = s.get_history(max_messages=10)
        assert len(history) == 10
        assert history[-1]["content"] == "msg 49"

    def test_get_history_with_token_budget(self):
        s = Session(key="test:chat_A")
        s.add_message("user", "short msg")
        history = s.get_history(max_tokens=1000)
        assert len(history) >= 1


class TestSessionManager:
    def test_create_and_retrieve(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = SessionManager(Path(tmpdir))
            s = mgr.get_or_create("test:chat_A")
            assert s.key == "test:chat_A"
            s2 = mgr.get_or_create("test:chat_A")
            assert s2 is s  # Same object returned

    def test_save_and_persist(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = SessionManager(Path(tmpdir))
            s = mgr.get_or_create("test:chat_B")
            s.add_message("user", "persist me")
            mgr.save(s)

            # Create new manager to test persistence
            mgr2 = SessionManager(Path(tmpdir))
            s2 = mgr2.get_or_create("test:chat_B")
            assert len(s2.messages) == 1
            assert s2.messages[0]["content"] == "persist me"

    def test_clear_session(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = SessionManager(Path(tmpdir))
            s = mgr.get_or_create("test:chat_C")
            s.add_message("user", "hello")
            mgr.save(s)
            mgr.clear("test:chat_C")
            s2 = mgr.get_or_create("test:chat_C")
            assert len(s2.messages) == 0

    def test_isolation_by_key(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = SessionManager(Path(tmpdir))
            s1 = mgr.get_or_create("test:chat_A")
            s2 = mgr.get_or_create("test:chat_B")
            s1.add_message("user", "A's message")
            s2.add_message("user", "B's message")
            mgr.save(s1)
            mgr.save(s2)

            mgr2 = SessionManager(Path(tmpdir))
            a = mgr2.get_or_create("test:chat_A")
            b = mgr2.get_or_create("test:chat_B")
            assert a.messages[0]["content"] == "A's message"
            assert b.messages[0]["content"] == "B's message"
```

- [ ] **Step 2: Implement session/manager.py**

```python
"""Session manager — per-chat_id conversation persistence with SQLite."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class Session:
    """A single conversation session, keyed by chat_id."""

    def __init__(self, key: str, messages: list[dict[str, Any]] | None = None,
                 metadata: dict[str, Any] | None = None):
        self.key = key
        self.messages: list[dict[str, Any]] = messages or []
        self.metadata: dict[str, Any] = metadata or {}
        self.created_at = datetime.now(timezone.utc)
        self.updated_at = datetime.now(timezone.utc)

    def add_message(self, role: str, content: str, **extra) -> None:
        """Add a message to the session history."""
        entry = {"role": role, "content": content, "timestamp": datetime.now(timezone.utc).isoformat()}
        entry.update(extra)
        self.messages.append(entry)
        self.updated_at = datetime.now(timezone.utc)

    def get_history(
        self,
        max_messages: int = 50,
        max_tokens: int | None = None,
        include_timestamps: bool = False,
    ) -> list[dict[str, Any]]:
        """Return recent messages as LLM-compatible dicts."""
        recent = self.messages[-max_messages:]
        result = []
        for m in recent:
            entry = {"role": m["role"], "content": m["content"]}
            if include_timestamps:
                entry["timestamp"] = m.get("timestamp", "")
            result.append(entry)

        # Token budget trimming (simple: ~4 chars per token)
        if max_tokens:
            total = 0
            trimmed = []
            for m in reversed(result):
                content = m.get("content", "")
                total += len(str(content)) // 4 + 4
                if total > max_tokens:
                    break
                trimmed.insert(0, m)
            return trimmed

        return result


class SessionManager:
    """Manages conversation sessions with SQLite persistence."""

    def __init__(self, data_dir: Path):
        self._data_dir = Path(data_dir)
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._db_path = self._data_dir / "sessions.db"
        self._cache: dict[str, Session] = {}
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(str(self._db_path)) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    key TEXT PRIMARY KEY,
                    messages_json TEXT DEFAULT '[]',
                    metadata_json TEXT DEFAULT '{}',
                    created_at TEXT,
                    updated_at TEXT
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_sessions_updated
                ON sessions(updated_at)
            """)
            conn.commit()

    def get_or_create(self, key: str) -> Session:
        with self._lock:
            if key in self._cache:
                return self._cache[key]

            # Try loading from DB
            with sqlite3.connect(str(self._db_path)) as conn:
                row = conn.execute(
                    "SELECT messages_json, metadata_json FROM sessions WHERE key = ?",
                    (key,),
                ).fetchone()

            if row:
                messages = json.loads(row[0])
                metadata = json.loads(row[1])
                session = Session(key=key, messages=messages, metadata=metadata)
            else:
                session = Session(key=key)

            self._cache[key] = session
            return session

    def save(self, session: Session) -> None:
        with self._lock:
            with sqlite3.connect(str(self._db_path)) as conn:
                conn.execute(
                    """INSERT OR REPLACE INTO sessions
                       (key, messages_json, metadata_json, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?)""",
                    (
                        session.key,
                        json.dumps(session.messages, ensure_ascii=False),
                        json.dumps(session.metadata, ensure_ascii=False),
                        session.created_at.isoformat(),
                        datetime.now(timezone.utc).isoformat(),
                    ),
                )
                conn.commit()

    def clear(self, key: str) -> None:
        with self._lock:
            self._cache.pop(key, None)
            with sqlite3.connect(str(self._db_path)) as conn:
                conn.execute("DELETE FROM sessions WHERE key = ?", (key,))
                conn.commit()

    def delete(self, key: str) -> None:
        self.clear(key)

    def all_keys(self) -> list[str]:
        with sqlite3.connect(str(self._db_path)) as conn:
            rows = conn.execute("SELECT key FROM sessions").fetchall()
            return [r[0] for r in rows]
```

```python
# swarm/session/__init__.py
from swarm.session.manager import Session, SessionManager

__all__ = ["Session", "SessionManager"]
```

- [ ] **Step 3: Run tests and commit**

```bash
pytest tests/test_session.py -v
git add swarm/session/ tests/test_session.py
git commit -m "feat: add session manager (SQLite persistence, per-chat_id isolation)"
```

---

### Task 10: Memory System

**Files:**
- Create: `swarm/swarm/memory/__init__.py`
- Create: `swarm/swarm/memory/store.py`
- Create: `swarm/swarm/memory/short_term.py`
- Create: `swarm/swarm/memory/dream.py`
- Create: `swarm/swarm/memory/recall.py`
- Create: `swarm/tests/test_memory.py`

- [ ] **Step 1: Write memory tests**

```python
# tests/test_memory.py
import pytest
import tempfile
from pathlib import Path
from swarm.memory.store import ChromaMemoryStore
from swarm.memory.short_term import ShortTermMemory
from swarm.memory.recall import MemoryRecall


class TestShortTermMemory:
    def test_add_and_query(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = ShortTermMemory(Path(tmpdir))
            store.add("chat_A", "user_1", "Hello world")
            store.add("chat_A", "assistant", "Hi there!")
            recent = store.get_recent("chat_A", limit=10)
            assert len(recent) == 2

    def test_isolation(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = ShortTermMemory(Path(tmpdir))
            store.add("chat_A", "user_1", "A's message")
            store.add("chat_B", "user_2", "B's message")
            a_msgs = store.get_recent("chat_A", limit=10)
            b_msgs = store.get_recent("chat_B", limit=10)
            assert len(a_msgs) == 1
            assert len(b_msgs) == 1
            assert "A's message" in str(a_msgs[0])
            assert "B's message" in str(b_msgs[0])

    def test_count_since_consolidation(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = ShortTermMemory(Path(tmpdir))
            for i in range(25):
                store.add("chat_A", "user_1", f"msg {i}")
            assert store.count_since_consolidation("chat_A") == 25


class TestMemoryRecall:
    def test_hybrid_recall_empty(self):
        recall = MemoryRecall(use_chromadb=False)
        results = recall.query("test query", chat_id="chat_A", k=5)
        assert results == []

    def test_recall_with_metadata(self):
        recall = MemoryRecall(use_chromadb=False)
        recall._index.append({
            "content": "User works at Acme Corp",
            "chat_id": "chat_A",
            "user_id": "user_1",
            "importance": 1.0,
            "timestamp": "2026-01-01T00:00:00",
        })
        results = recall.query("where does user work", chat_id="chat_A", k=5)
        # In fallback mode (no ChromaDB), results may be empty
        assert isinstance(results, list)
```

- [ ] **Step 2: Implement memory modules**

```python
# swarm/memory/store.py
"""ChromaDB vector memory store — collections per chat_id for isolation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

try:
    import chromadb
    from chromadb.config import Settings
    HAS_CHROMADB = True
except ImportError:
    HAS_CHROMADB = False


class ChromaMemoryStore:
    """Vector memory store using ChromaDB. Each chat_id gets its own collection."""

    def __init__(self, persist_dir: str | Path, embedding_model: str = "all-MiniLM-L6-v2"):
        self._persist_dir = Path(persist_dir)
        self._persist_dir.mkdir(parents=True, exist_ok=True)
        self._embedding_model = embedding_model
        self._client = None
        if HAS_CHROMADB:
            try:
                import chromadb.utils.embedding_functions as ef
                self._ef = ef.SentenceTransformerEmbeddingFunction(
                    model_name=embedding_model,
                )
                self._client = chromadb.PersistentClient(
                    path=str(self._persist_dir),
                    settings=Settings(anonymized_telemetry=False),
                )
            except Exception:
                logger.warning("ChromaDB init failed — memory disabled", exc_info=True)
                self._client = None

    def _collection_name(self, chat_id: str) -> str:
        """Derive collection name from chat_id for isolation."""
        safe = chat_id.replace(":", "_").replace("/", "_")
        return f"mem_{safe}"

    async def add(self, chat_id: str, user_id: str, content: str,
                  importance: float = 0.5, metadata: dict | None = None) -> bool:
        """Add a memory entry to the vector store."""
        if self._client is None:
            return False
        try:
            col = self._client.get_or_create_collection(
                name=self._collection_name(chat_id),
                embedding_function=self._ef,
            )
            meta = {"user_id": user_id, "importance": importance,
                    "timestamp": __import__("datetime").datetime.now().isoformat()}
            if metadata:
                meta.update(metadata)
            col.add(documents=[content], metadatas=[meta], ids=[f"{chat_id}_{__import__('uuid').uuid4()}"])
            return True
        except Exception:
            logger.exception("Failed to add memory entry")
            return False

    async def query(self, chat_id: str, query_text: str, k: int = 10) -> list[dict[str, Any]]:
        """Query vector store for semantically similar memories."""
        if self._client is None:
            return []
        try:
            col_name = self._collection_name(chat_id)
            try:
                col = self._client.get_collection(name=col_name, embedding_function=self._ef)
            except Exception:
                return []
            results = col.query(query_texts=[query_text], n_results=k)
            if not results or not results.get("documents") or not results["documents"][0]:
                return []
            entries = []
            for i, doc in enumerate(results["documents"][0]):
                meta = results["metadatas"][0][i] if results.get("metadatas") else {}
                entries.append({"content": doc, "metadata": meta})
            return entries
        except Exception:
            return []

    async def delete_collection(self, chat_id: str) -> None:
        """Delete all memories for a chat_id."""
        if self._client is None:
            return
        try:
            self._client.delete_collection(name=self._collection_name(chat_id))
        except Exception:
            pass
```

```python
# swarm/memory/short_term.py
"""SQLite short-term message store — partitioned by chat_id."""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any


class ShortTermMemory:
    """Short-term message storage with per-chat_id partitioning."""

    def __init__(self, data_dir: Path):
        self._data_dir = Path(data_dir)
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._db_path = self._data_dir / "short_term.db"
        self._consolidation_cursor: dict[str, int] = {}
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(str(self._db_path)) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at REAL NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_msg_chat ON messages(chat_id, created_at)")
            conn.commit()

    def add(self, chat_id: str, user_id: str, content: str, role: str = "user") -> None:
        with sqlite3.connect(str(self._db_path)) as conn:
            conn.execute(
                "INSERT INTO messages (chat_id, user_id, role, content, created_at) VALUES (?, ?, ?, ?, ?)",
                (chat_id, user_id, role, content, time.time()),
            )
            conn.commit()

    def get_recent(self, chat_id: str, limit: int = 50) -> list[dict[str, Any]]:
        with sqlite3.connect(str(self._db_path)) as conn:
            rows = conn.execute(
                "SELECT user_id, role, content, created_at FROM messages WHERE chat_id = ? ORDER BY created_at DESC LIMIT ?",
                (chat_id, limit),
            ).fetchall()
        return [
            {"user_id": r[0], "role": r[1], "content": r[2], "timestamp": r[3]}
            for r in reversed(rows)
        ]

    def get_unprocessed(self, chat_id: str, since_id: int = 0) -> list[dict[str, Any]]:
        with sqlite3.connect(str(self._db_path)) as conn:
            rows = conn.execute(
                "SELECT id, user_id, role, content FROM messages WHERE chat_id = ? AND id > ? ORDER BY id",
                (chat_id, since_id),
            ).fetchall()
        return [{"id": r[0], "user_id": r[1], "role": r[2], "content": r[3]} for r in rows]

    def count_since_consolidation(self, chat_id: str) -> int:
        cursor = self._consolidation_cursor.get(chat_id, 0)
        with sqlite3.connect(str(self._db_path)) as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM messages WHERE chat_id = ? AND id > ?",
                (chat_id, cursor),
            ).fetchone()
            return row[0] if row else 0

    def mark_consolidated(self, chat_id: str, up_to_id: int) -> None:
        self._consolidation_cursor[chat_id] = up_to_id

    def cleanup(self, chat_id: str, ttl_seconds: float = 7 * 86400) -> int:
        cutoff = time.time() - ttl_seconds
        with sqlite3.connect(str(self._db_path)) as conn:
            cur = conn.execute(
                "DELETE FROM messages WHERE chat_id = ? AND created_at < ?",
                (chat_id, cutoff),
            )
            conn.commit()
            return cur.rowcount
```

```python
# swarm/memory/recall.py
"""Hybrid memory recall — vector similarity + time decay + importance weighting."""

from __future__ import annotations

import math
import time
from pathlib import Path
from typing import Any


class MemoryRecall:
    """Hybrid recall combining vector search and fallback keyword matching."""

    def __init__(self, chroma_store=None, short_term=None, use_chromadb: bool = True):
        self._chroma = chroma_store
        self._short_term = short_term
        self._use_chromadb = use_chromadb
        self._index: list[dict] = []  # Fallback when ChromaDB unavailable

    async def query(self, query_text: str, chat_id: str, k: int = 10,
                    time_decay_days: float = 30.0) -> list[dict[str, Any]]:
        """Hybrid recall for a given query and chat_id."""
        results = []

        # ChromaDB vector search (primary)
        if self._chroma and self._use_chromadb:
            try:
                chroma_results = await self._chroma.query(chat_id, query_text, k=k)
                results.extend(chroma_results)
            except Exception:
                pass

        # Apply time decay weighting
        now = time.time()
        for r in results:
            ts_str = (r.get("metadata") or {}).get("timestamp", "")
            importance = float((r.get("metadata") or {}).get("importance", 0.5))
            try:
                if ts_str:
                    msg_time = __import__('datetime').datetime.fromisoformat(ts_str).timestamp()
                else:
                    msg_time = now
            except (ValueError, TypeError):
                msg_time = now
            age_days = max(0, (now - msg_time) / 86400)
            time_weight = math.exp(-age_days / max(1, time_decay_days))
            r["_score"] = importance * time_weight

        # Sort by score descending
        results.sort(key=lambda r: r.get("_score", 0), reverse=True)
        return results[:k]
```

```python
# swarm/memory/__init__.py
from swarm.memory.store import ChromaMemoryStore
from swarm.memory.short_term import ShortTermMemory
from swarm.memory.recall import MemoryRecall

__all__ = ["ChromaMemoryStore", "ShortTermMemory", "MemoryRecall"]
```

- [ ] **Step 3: Run tests and commit**

```bash
pytest tests/test_memory.py -v
git add swarm/memory/ tests/test_memory.py
git commit -m "feat: add memory system (ChromaDB + short-term SQLite + hybrid recall)"
```

---

### Task 11: Tools System

**Files:**
- Create: `swarm/swarm/tools/__init__.py`
- Create: `swarm/swarm/tools/base.py`
- Create: `swarm/swarm/tools/registry.py`
- Create: `swarm/swarm/tools/builtin/__init__.py`
- Create: `swarm/swarm/tools/builtin/message.py`
- Create: `swarm/swarm/tools/builtin/web_search.py`
- Create: `swarm/swarm/tools/builtin/system.py`
- Create: `swarm/tests/test_tools.py`

- [ ] **Step 1: Write tools tests**

```python
# tests/test_tools.py
import pytest
from swarm.tools.base import ToolBase, tool_result
from swarm.tools.registry import ToolRegistry
from swarm.agent.context import RequestContext


def test_tool_result():
    result = tool_result("success", data={"key": "value"})
    assert "success" in result
    assert "key" in result


class EchoTool(ToolBase):
    name = "echo"
    description = "Echo back the input"
    parameters = {
        "type": "object",
        "properties": {"text": {"type": "string", "description": "Text to echo"}},
        "required": ["text"],
    }

    async def execute(self, args: dict, ctx: RequestContext) -> str:
        return tool_result(args.get("text", ""))


class TestToolRegistry:
    def test_register_and_list(self):
        reg = ToolRegistry()
        reg.register(EchoTool())
        assert "echo" in reg.tool_names
        assert len(reg.tool_names) == 1

    def test_get_definitions(self):
        reg = ToolRegistry()
        reg.register(EchoTool())
        defs = reg.get_definitions()
        assert len(defs) == 1
        assert defs[0]["function"]["name"] == "echo"

    @pytest.mark.asyncio
    async def test_execute(self):
        reg = ToolRegistry()
        reg.register(EchoTool())
        ctx = RequestContext(trace_id="t1", chat_id="c1", chat_type="p2p",
                            user_id="u1", message_id="m1")
        result = await reg.execute("echo", {"text": "hello world"})
        assert "hello world" in result

    def test_duplicate_register_raises(self):
        reg = ToolRegistry()
        reg.register(EchoTool())
        with pytest.raises(ValueError):
            reg.register(EchoTool())

    def test_list_tools_returns_names(self):
        reg = ToolRegistry()
        reg.register(EchoTool())
        names = reg.tool_names
        assert isinstance(names, list)
        assert "echo" in names
```

- [ ] **Step 2: Implement tools/base.py and registry.py**

```python
# swarm/tools/base.py
"""Tool base class and utilities."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any

from swarm.agent.context import RequestContext


def tool_result(message: str, **kwargs) -> str:
    """Format a tool execution result as a string the LLM can understand."""
    if kwargs:
        parts = [message]
        for key, value in kwargs.items():
            parts.append(f"{key}: {json.dumps(value, ensure_ascii=False)}")
        return "\n".join(parts)
    return message


class ToolBase(ABC):
    """Base class for all Swarm tools."""

    name: str = ""
    description: str = ""
    parameters: dict[str, Any] = {"type": "object", "properties": {}}
    permissions: set[str] = set()

    def get_definition(self) -> dict[str, Any]:
        """Generate the OpenAI tool definition for this tool."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    @abstractmethod
    async def execute(self, args: dict[str, Any], ctx: RequestContext) -> str:
        """Execute the tool with the given arguments and request context."""
        ...

    def check_permission(self, ctx: RequestContext) -> bool:
        """Check whether the request has permission to use this tool."""
        if not self.permissions:
            return True
        return bool(self.permissions & ctx.permissions)
```

```python
# swarm/tools/registry.py
"""Tool registry — registration, lookup, execution, LLM definitions."""

from __future__ import annotations

from typing import Any

import structlog

from swarm.agent.context import RequestContext
from swarm.tools.base import ToolBase, tool_result

logger = structlog.get_logger(__name__)


class ToolRegistry:
    """Central registry for all tools."""

    def __init__(self):
        self._tools: dict[str, ToolBase] = {}

    @property
    def tool_names(self) -> list[str]:
        return list(self._tools.keys())

    def register(self, tool: ToolBase) -> None:
        """Register a tool. Raises ValueError if name already exists."""
        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' already registered")
        self._tools[tool.name] = tool
        logger.debug("Tool registered", name=tool.name)

    def get(self, name: str) -> ToolBase | None:
        return self._tools.get(name)

    def get_definitions(self, ctx: RequestContext | None = None) -> list[dict[str, Any]]:
        """Get tool definitions suitable for LLM function calling."""
        defs = []
        for tool in self._tools.values():
            if ctx and not tool.check_permission(ctx):
                continue
            defs.append(tool.get_definition())
        return defs

    async def execute(self, name: str, args: dict[str, Any],
                      ctx: RequestContext | None = None) -> str:
        """Execute a tool by name. Returns the tool result string."""
        tool = self._tools.get(name)
        if tool is None:
            return tool_result(f"Error: unknown tool '{name}'")

        if ctx and not tool.check_permission(ctx):
            return tool_result(f"Error: permission denied for tool '{name}'")

        logger.info("Executing tool", name=name)
        try:
            result = await tool.execute(args, ctx)
            return result
        except Exception as e:
            logger.error("Tool execution failed", name=name, error=str(e))
            return tool_result(f"Error executing tool '{name}': {e}")
```

```python
# swarm/tools/builtin/system.py
"""System tools: /help, /status, /clear commands."""

from swarm.agent.context import RequestContext
from swarm.tools.base import ToolBase, tool_result


class SystemTool(ToolBase):
    name = "system_command"
    description = "Execute built-in system commands"
    parameters = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "enum": ["help", "status"],
                "description": "The system command to execute",
            }
        },
        "required": ["command"],
    }

    def __init__(self, agent_loop=None):
        self._loop = agent_loop

    async def execute(self, args: dict, ctx: RequestContext) -> str:
        cmd = args.get("command", "help")
        if cmd == "help":
            return tool_result("Available: /help, /status, /clear")
        elif cmd == "status":
            return tool_result(f"Session: {ctx.chat_id}, Type: {ctx.chat_type}")
        return tool_result(f"Unknown command: {cmd}")
```

```python
# swarm/tools/builtin/web_search.py
"""Web search tool — DuckDuckGo (free) or Bing API (enterprise)."""

from __future__ import annotations

from swarm.agent.context import RequestContext
from swarm.tools.base import ToolBase, tool_result


class WebSearchTool(ToolBase):
    name = "web_search"
    description = "Search the web for information"
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "The search query"},
            "num_results": {"type": "integer", "description": "Max results (1-10)", "default": 5},
        },
        "required": ["query"],
    }

    def __init__(self, backend: str = "duckduckgo"):
        self._backend = backend

    async def execute(self, args: dict, ctx: RequestContext) -> str:
        query = args.get("query", "")
        num = min(int(args.get("num_results", 5)), 10)

        try:
            if self._backend == "duckduckgo":
                return await self._search_ddg(query, num)
            else:
                return tool_result(f"Search backend '{self._backend}' not implemented")
        except Exception as e:
            return tool_result(f"Search failed: {e}")

    async def _search_ddg(self, query: str, num: int) -> str:
        """Search using DuckDuckGo HTML (no API key needed)."""
        import httpx
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://html.duckduckgo.com/html/",
                params={"q": query},
                headers={"User-Agent": "Swarm/1.0"},
                timeout=10.0,
            )
            if resp.status_code != 200:
                return tool_result(f"Search returned status {resp.status_code}")

            # Very basic HTML result extraction
            text = resp.text
            results = []
            # Simple extraction: look for result snippets
            import re
            snippets = re.findall(r'class="result__snippet"[^>]*>(.*?)</a>', text, re.DOTALL)
            for i, s in enumerate(snippets[:num]):
                clean = re.sub(r'<[^>]+>', '', s).strip()
                if clean:
                    results.append(f"{i+1}. {clean}")

            if not results:
                return tool_result(f"No results found for '{query}'")

            return tool_result("\n".join(results))
```

```python
# swarm/tools/__init__.py
from swarm.tools.base import ToolBase, tool_result
from swarm.tools.registry import ToolRegistry

__all__ = ["ToolBase", "ToolRegistry", "tool_result"]
```

- [ ] **Step 3: Run tests and commit**

```bash
pytest tests/test_tools.py -v
git add swarm/tools/ tests/test_tools.py
git commit -m "feat: add tools system (registry + base + builtin web_search/system)"
```

---

### Task 12: Auth System

**Files:**
- Create: `swarm/swarm/auth/__init__.py`
- Create: `swarm/swarm/auth/token_store.py`
- Create: `swarm/swarm/auth/oauth.py`
- Create: `swarm/swarm/auth/callback_server.py`
- Create: `swarm/tests/test_auth.py`

- [ ] **Step 1: Write auth tests**

```python
# tests/test_auth.py
import pytest
import tempfile
from pathlib import Path
from swarm.auth.token_store import TokenStore, TokenData


class TestTokenStore:
    def test_save_and_lookup(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = TokenStore(Path(tmpdir), encrypt_key="test-key-32-bytes-long!!")
            store.save("user_1", TokenData(
                access_token="acc_xxx",
                refresh_token="ref_yyy",
                expires_at=9999999999,
            ))
            token = store.lookup("user_1")
            assert token is not None
            assert token.access_token == "acc_xxx"
            assert token.refresh_token == "ref_yyy"

    def test_lookup_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = TokenStore(Path(tmpdir), encrypt_key="test-key-32-bytes-long!!")
            assert store.lookup("user_nonexistent") is None

    def test_delete(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = TokenStore(Path(tmpdir), encrypt_key="test-key-32-bytes-long!!")
            store.save("user_1", TokenData(access_token="x", refresh_token="y", expires_at=0))
            store.delete("user_1")
            assert store.lookup("user_1") is None

    def test_is_authorized(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = TokenStore(Path(tmpdir), encrypt_key="test-key-32-bytes-long!!")
            assert not store.is_authorized("user_1")
            store.save("user_1", TokenData(access_token="x", refresh_token="y",
                                           expires_at=9999999999))
            assert store.is_authorized("user_1")

    def test_encryption_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = TokenStore(Path(tmpdir), encrypt_key="super-secret-key-32bytes!")
            original = TokenData(
                access_token="very-secret-token",
                refresh_token="very-secret-refresh",
                expires_at=9999999999,
            )
            store.save("user_1", original)
            restored = store.lookup("user_1")
            assert restored.access_token == original.access_token
            assert restored.refresh_token == original.refresh_token
```

- [ ] **Step 2: Implement auth/token_store.py**

```python
"""Encrypted SQLite token storage — AES-256-GCM encryption for refresh tokens."""

from __future__ import annotations

import base64
import json
import os
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class TokenData:
    access_token: str
    refresh_token: str
    expires_at: float  # Unix timestamp

    def is_expired(self, buffer_seconds: float = 300) -> bool:
        """Check if access token is expired (with buffer)."""
        return time.time() + buffer_seconds >= self.expires_at


class TokenStore:
    """AES-encrypted SQLite storage for Feishu user OAuth tokens."""

    def __init__(self, data_dir: Path, encrypt_key: str):
        self._data_dir = Path(data_dir)
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._db_path = self._data_dir / "tokens.db"

        # Derive a 32-byte key from the provided key
        key_bytes = encrypt_key.encode("utf-8")
        if len(key_bytes) < 32:
            key_bytes = key_bytes.ljust(32, b"\x00")[:32]
        else:
            key_bytes = key_bytes[:32]
        self._key = key_bytes
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(str(self._db_path)) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tokens (
                    user_id TEXT PRIMARY KEY,
                    encrypted_data TEXT NOT NULL,
                    updated_at REAL NOT NULL
                )
            """)
            conn.commit()

    def _encrypt(self, plaintext: str) -> str:
        """Encrypt a string with AES-256-GCM."""
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        nonce = os.urandom(12)
        aesgcm = AESGCM(self._key)
        ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
        combined = nonce + ciphertext
        return base64.b64encode(combined).decode("ascii")

    def _decrypt(self, encoded: str) -> str:
        """Decrypt an AES-256-GCM encrypted string."""
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        combined = base64.b64decode(encoded)
        nonce = combined[:12]
        ciphertext = combined[12:]
        aesgcm = AESGCM(self._key)
        plaintext = aesgcm.decrypt(nonce, ciphertext, None)
        return plaintext.decode("utf-8")

    def save(self, user_id: str, token: TokenData) -> None:
        data = json.dumps({
            "access_token": token.access_token,
            "refresh_token": token.refresh_token,
            "expires_at": token.expires_at,
        })
        encrypted = self._encrypt(data)
        with sqlite3.connect(str(self._db_path)) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO tokens (user_id, encrypted_data, updated_at) VALUES (?, ?, ?)",
                (user_id, encrypted, time.time()),
            )
            conn.commit()
        logger.info("Token saved", user_id=user_id)

    def lookup(self, user_id: str) -> TokenData | None:
        with sqlite3.connect(str(self._db_path)) as conn:
            row = conn.execute(
                "SELECT encrypted_data FROM tokens WHERE user_id = ?", (user_id,)
            ).fetchone()
        if not row:
            return None
        try:
            plain = self._decrypt(row[0])
            data = json.loads(plain)
            return TokenData(
                access_token=data["access_token"],
                refresh_token=data["refresh_token"],
                expires_at=data["expires_at"],
            )
        except Exception:
            logger.exception("Failed to decrypt token", user_id=user_id)
            return None

    def delete(self, user_id: str) -> None:
        with sqlite3.connect(str(self._db_path)) as conn:
            conn.execute("DELETE FROM tokens WHERE user_id = ?", (user_id,))
            conn.commit()

    def is_authorized(self, user_id: str) -> bool:
        token = self.lookup(user_id)
        return token is not None
```

```python
# swarm/auth/__init__.py
from swarm.auth.token_store import TokenData, TokenStore

__all__ = ["TokenStore", "TokenData"]
```

- [ ] **Step 3: Run tests and commit**

```bash
pytest tests/test_auth.py -v
git add swarm/auth/ tests/test_auth.py
git commit -m "feat: add auth system (encrypted token store)"
```

---

### Task 13: Gateway — Feishu WebSocket

**Files:**
- Create: `swarm/swarm/gateway/__init__.py`
- Create: `swarm/swarm/gateway/feishu_ws.py`
- Create: `swarm/swarm/gateway/feishu_message.py`
- Create: `swarm/swarm/gateway/feishu_reply.py`
- Create: `swarm/tests/test_feishu_message.py`

- [ ] **Step 1: Write feishu message tests**

```python
# tests/test_feishu_message.py
import json
from swarm.gateway.feishu_message import parse_message_content, MSG_TYPE_MAP


class TestMessageParser:
    def test_text_message(self):
        content = json.dumps({"text": "Hello, Swarm!"})
        text, images = parse_message_content("text", content)
        assert text == "Hello, Swarm!"
        assert images == []

    def test_image_message(self):
        content = json.dumps({"image_key": "img_abc123"})
        text, images = parse_message_content("image", content)
        assert "[image]" in text.lower()
        assert "img_abc123" in images

    def test_audio_message(self):
        content = json.dumps({"file_key": "file_xxx"})
        text, images = parse_message_content("audio", content)
        assert "[audio]" in text.lower()

    def test_sticker_message(self):
        text, images = parse_message_content("sticker", "{}")
        assert "[sticker]" in text.lower()

    def test_post_message_extracts_text(self):
        content = json.dumps({
            "title": "Test Post",
            "content": [
                [{"tag": "text", "text": "Hello from post"}],
            ],
        })
        text, images = parse_message_content("post", content)
        assert "Hello from post" in text

    def test_unknown_type(self):
        text, images = parse_message_content("unknown_type", "{}")
        assert "[unknown_type]" in text.lower()


class TestMsgTypeMap:
    def test_all_known_types(self):
        known = {"image", "audio", "file", "sticker"}
        for k in known:
            assert k in MSG_TYPE_MAP
```

- [ ] **Step 2: Implement gateway modules**

```python
# swarm/gateway/__init__.py
"""Feishu gateway — WebSocket, message parsing, reply construction."""
```

```python
# swarm/gateway/feishu_message.py
"""Feishu message content parser — handles all msg_types."""

from __future__ import annotations

import json
from typing import Any

MSG_TYPE_MAP = {
    "image": "[image]",
    "audio": "[audio]",
    "file": "[file]",
    "sticker": "[sticker]",
}


def parse_message_content(msg_type: str, content_json: str) -> tuple[str, list[str]]:
    """Parse Feishu message content into (text, image_keys)."""
    try:
        content = json.loads(content_json) if isinstance(content_json, str) else content_json
    except (json.JSONDecodeError, TypeError):
        return content_json if isinstance(content_json, str) else "", []

    if msg_type == "text":
        return content.get("text", ""), []

    elif msg_type == "post":
        text, images = _extract_post_content(content)
        return text or "[post message]", images

    elif msg_type == "image":
        image_key = content.get("image_key", "")
        return "[image]", [image_key] if image_key else []

    elif msg_type == "audio":
        return "[audio]", []

    elif msg_type == "file":
        return f"[file: {content.get('file_name', 'unknown')}]", []

    elif msg_type == "sticker":
        return "[sticker]", []

    elif msg_type in ("share_chat", "share_user", "share_calendar_event"):
        return f"[{msg_type}]", []

    elif msg_type == "interactive":
        return _extract_card_text(content), []

    elif msg_type == "system":
        return "", []  # Ignore system messages

    elif msg_type == "merge_forward":
        return "[merged forward messages]", []

    else:
        return f"[{msg_type}]", []


def _extract_post_content(content: dict) -> tuple[str, list[str]]:
    """Extract text and image keys from a Feishu post (rich text) message."""
    texts = []
    images = []

    root = content
    if isinstance(root, dict) and isinstance(root.get("post"), dict):
        root = root["post"]

    if isinstance(root.get("title"), str) and root["title"]:
        texts.append(root["title"])

    body = root.get("content", root)
    if isinstance(body, list):
        for paragraph in body:
            if not isinstance(paragraph, list):
                continue
            for element in paragraph:
                if not isinstance(element, dict):
                    continue
                tag = element.get("tag", "")
                if tag == "text":
                    texts.append(element.get("text", ""))
                elif tag == "a":
                    texts.append(element.get("text", ""))
                    if href := element.get("href"):
                        texts.append(f"({href})")
                elif tag == "at":
                    user = element.get("user_name", "user")
                    texts.append(f"@{user}")
                elif tag == "img":
                    if key := element.get("image_key"):
                        images.append(key)

    return " ".join(texts).strip(), images


def _extract_card_text(content: dict) -> str:
    """Extract readable text from interactive card content."""
    parts = []
    if isinstance(content.get("title"), str):
        parts.append(content["title"])
    # Recursively extract text from card elements
    _walk_card_elements(content, parts)
    return "\n".join(parts) if parts else "[interactive card]"


def _walk_card_elements(node: Any, parts: list[str]) -> None:
    """Recursively extract text from card element nodes."""
    if isinstance(node, str):
        if node.strip():
            parts.append(node)
    elif isinstance(node, dict):
        for key in ("content", "text", "title"):
            if val := node.get(key):
                _walk_card_elements(val, parts)
        for key in ("elements", "fields", "columns"):
            if lst := node.get(key):
                if isinstance(lst, list):
                    for item in lst:
                        _walk_card_elements(item, parts)
        if tag := node.get("tag"):
            if tag == "a" and (href := node.get("href")):
                parts.append(href)
    elif isinstance(node, list):
        for item in node:
            _walk_card_elements(item, parts)
```

```python
# swarm/gateway/feishu_ws.py
"""Feishu WebSocket long connection — connect, reconnect, event dispatch."""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Callable

import structlog

from swarm.bus.queue import MessageBus, InboundMessage
from swarm.gateway.feishu_message import parse_message_content

logger = structlog.get_logger(__name__)


class FeishuWebSocket:
    """Feishu WebSocket client using lark-oapi SDK."""

    def __init__(
        self,
        app_id: str,
        app_secret: str,
        bus: MessageBus,
        domain: str = "feishu",
    ):
        self._app_id = app_id
        self._app_secret = app_secret
        self._bus = bus
        self._domain = domain
        self._running = False
        self._ws = None
        self._reconnect_delay = 1.0
        self._max_reconnect_delay = 60.0

    async def start(self) -> None:
        """Start the WebSocket connection loop."""
        self._running = True
        logger.info("Feishu WebSocket starting", app_id=self._app_id)

        while self._running:
            try:
                await self._connect_and_listen()
            except Exception as e:
                logger.error("WebSocket error, reconnecting", error=str(e))
                if self._running:
                    await asyncio.sleep(self._reconnect_delay)
                    self._reconnect_delay = min(
                        self._reconnect_delay * 2,
                        self._max_reconnect_delay,
                    )

    async def _connect_and_listen(self) -> None:
        """Connect to Feishu WebSocket and process events."""
        from lark_oapi.ws import Client as WsClient

        client = WsClient(
            app_id=self._app_id,
            app_secret=self._app_secret,
            domain=self._domain,
        )

        async for event in client:
            if not self._running:
                break

            self._reconnect_delay = 1.0  # Reset on success

            try:
                await self._handle_event(event)
            except Exception as e:
                logger.error("Error handling event", error=str(e))

    async def _handle_event(self, event: Any) -> None:
        """Dispatch a Feishu WebSocket event to the message bus."""
        event_type = getattr(event, 'type', '')

        # Only process message receive events
        if 'im.message.receive_v1' not in str(event_type):
            return

        # Extract event data
        msg_data = {}
        if hasattr(event, 'event'):
            msg_data = event.event or {}
        elif isinstance(event, dict):
            msg_data = event

        message = msg_data.get('message', {})
        if not message:
            return

        msg_type = message.get('message_type', 'text')
        content = message.get('content', '{}')
        msg_id = message.get('message_id', '')
        chat_id = message.get('chat_id', '')
        chat_type = message.get('chat_type', 'p2p')

        sender = msg_data.get('sender', {})
        sender_id = sender.get('sender_id', {})
        if isinstance(sender_id, dict):
            sender_id = sender_id.get('open_id', '')
        elif isinstance(sender_id, str):
            sender_id = sender_id

        # Parse message content
        text, images = parse_message_content(msg_type, content)

        if not text and not images:
            return  # Skip empty messages (e.g., system events)

        inbound = InboundMessage(
            channel="feishu",
            sender_id=str(sender_id),
            chat_id=str(chat_id),
            content=text or "",
            media=images,
            metadata={
                "message_id": str(msg_id),
                "chat_type": str(chat_type),
                "msg_type": msg_type,
            },
        )

        await self._bus.publish_inbound(inbound)
        logger.debug("Message received", chat_id=chat_id, msg_type=msg_type)

    async def stop(self) -> None:
        """Stop the WebSocket connection."""
        self._running = False
        logger.info("Feishu WebSocket stopping")
```

```python
# swarm/gateway/feishu_reply.py
"""Feishu outbound message builder — text, card, streaming support."""

from __future__ import annotations

from typing import Any

import httpx
import structlog

logger = structlog.get_logger(__name__)


class FeishuReply:
    """Build and send Feishu message replies."""

    def __init__(self, app_id: str, app_secret: str, domain: str = "feishu"):
        self._app_id = app_id
        self._app_secret = app_secret
        self._domain = domain
        self._tenant_token: str | None = None
        self._token_expires: float = 0

    async def _get_tenant_token(self) -> str:
        """Get or refresh tenant access token."""
        import time
        if self._tenant_token and time.time() < self._token_expires - 60:
            return self._tenant_token

        base = "https://open.feishu.cn" if self._domain == "feishu" else "https://open.larksuite.com"
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{base}/open-apis/auth/v3/tenant_access_token/internal",
                json={"app_id": self._app_id, "app_secret": self._app_secret},
                timeout=10.0,
            )
            data = resp.json()
            if data.get("code") != 0:
                raise RuntimeError(f"Failed to get tenant token: {data.get('msg')}")
            self._tenant_token = data["tenant_access_token"]
            self._token_expires = time.time() + data.get("expire", 7200)
            return self._tenant_token

    async def send_text(self, chat_id: str, content: str, msg_id: str | None = None) -> str | None:
        """Send a text reply message."""
        token = await self._get_tenant_token()
        base = "https://open.feishu.cn" if self._domain == "feishu" else "https://open.larksuite.com"

        body: dict[str, Any] = {
            "msg_type": "text",
            "content": json.dumps({"text": content}),
        }
        if msg_id:
            body["reply_in_thread"] = True

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{base}/open-apis/im/v1/messages/{chat_id}/reply",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json=body,
                timeout=10.0,
            )
            data = resp.json()
            if data.get("code") != 0:
                logger.error("Failed to send message", error=data.get("msg"))
                raise RuntimeError(f"Send failed: {data.get('msg')}")
            return data.get("data", {}).get("message_id")
```

- [ ] **Step 2: Run tests and commit**

```bash
pytest tests/test_feishu_message.py -v
git add swarm/gateway/ tests/test_feishu_message.py
git commit -m "feat: add feishu gateway (WebSocket + message parser + reply builder)"
```

---

### Task 14: CLI Interface

**Files:**
- Create: `swarm/swarm/cli/__init__.py`
- Create: `swarm/swarm/cli/main.py`
- Create: `swarm/swarm/cli/chat.py`
- Create: `swarm/swarm/cli/stream.py`

- [ ] **Step 1: Implement CLI**

```python
# swarm/cli/main.py
"""CLI entry point — swarm chat / swarm ws / swarm init."""

from __future__ import annotations

import asyncio
import sys

import typer
from rich.console import Console

from swarm import __version__, __logo__

app = typer.Typer(name="swarm", help="🐝 Swarm — Feishu AI Agent Framework")
console = Console()


@app.command()
def version() -> None:
    """Print version and exit."""
    console.print(__logo__, style="bold yellow")
    console.print(f"Swarm v{__version__}", style="green")


@app.command()
def chat(
    session: str = typer.Option("default", "--session", "-s", help="Session name"),
    config_path: str = typer.Option("config.yaml", "--config", "-c", help="Config file path"),
) -> None:
    """Start interactive chat mode."""
    from swarm.cli.chat import InteractiveChat
    from swarm.config.loader import load_config
    from swarm.providers.factory import make_provider

    try:
        config = load_config(config_path)
    except FileNotFoundError as e:
        console.print(f"[red]Error: {e}[/red]")
        console.print("Run 'swarm init' to create a config, or copy config.yaml.example")
        raise typer.Exit(1)

    provider = make_provider(config.llm)

    chat_app = InteractiveChat(provider=provider, session_name=session)
    asyncio.run(chat_app.run())


@app.command()
def ws(
    config_path: str = typer.Option("config.yaml", "--config", "-c", help="Config file path"),
) -> None:
    """Start Feishu WebSocket mode."""
    from swarm.bus.queue import MessageBus
    from swarm.config.loader import load_config
    from swarm.gateway.feishu_ws import FeishuWebSocket
    from swarm.providers.factory import make_provider
    from swarm.agent.loop import AgentLoop
    from swarm.session.manager import SessionManager
    from swarm.memory.store import ChromaMemoryStore
    from swarm.memory.short_term import ShortTermMemory
    from swarm.tools.registry import ToolRegistry
    from swarm.tools.builtin.web_search import WebSearchTool
    from swarm.tools.builtin.system import SystemTool
    from swarm.logging_.setup import setup_logging
    from pathlib import Path

    try:
        config = load_config(config_path)
    except FileNotFoundError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)

    # Setup logging
    setup_logging(
        level=config.logging.level,
        json_format=config.logging.json_format,
        log_dir=config.logging.log_dir,
        retention_days=config.logging.retention_days,
        compress=config.logging.compress,
        audit_enabled=config.logging.audit_enabled,
        error_separate=config.logging.error_separate,
    )

    # Setup components
    bus = MessageBus()
    provider = make_provider(config.llm)
    data_dir = Path(config.memory.chroma_path).parent

    tools = ToolRegistry()
    if config.tools.web_search.enabled:
        tools.register(WebSearchTool())
    tools.register(SystemTool())

    sessions = SessionManager(data_dir)
    chroma = ChromaMemoryStore(config.memory.chroma_path)
    short_term = ShortTermMemory(data_dir)

    loop = AgentLoop(
        bus=bus,
        provider=provider,
        workspace=data_dir,
        tools=tools,
        sessions=sessions,
    )

    feishu = FeishuWebSocket(
        app_id=config.feishu.app_id,
        app_secret=config.feishu.app_secret,
        bus=bus,
        domain=config.feishu.domain,
    )

    async def run_all():
        import signal
        loop_task = asyncio.create_task(loop.run())
        ws_task = asyncio.create_task(feishu.start())

        # Graceful shutdown
        stop_event = asyncio.Event()

        def _signal_handler():
            stop_event.set()

        loop_ = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop_.add_signal_handler(sig, _signal_handler)

        await stop_event.wait()
        console.print("[yellow]Shutting down...[/yellow]")
        await loop.shutdown(timeout=10.0)
        await feishu.stop()
        loop_task.cancel()
        ws_task.cancel()

    try:
        asyncio.run(run_all())
    except KeyboardInterrupt:
        pass


@app.command()
def init() -> None:
    """Interactive configuration wizard."""
    from pathlib import Path
    import shutil

    console.print(__logo__, style="bold yellow")
    console.print("🐝 Swarm Initialization Wizard\n")

    # Check if config exists
    config_path = Path.cwd() / "config.yaml"
    if config_path.exists():
        overwrite = typer.confirm("config.yaml already exists. Overwrite?")
        if not overwrite:
            console.print("[yellow]Aborted.[/yellow]")
            return

    # Copy example config
    import importlib.resources
    try:
        example = importlib.resources.read_text("swarm", "config.yaml.example")
        config_path.write_text(example)
        console.print(f"[green]✓[/green] Created {config_path}")
    except Exception:
        console.print("[red]Failed to create config file[/red]")
        return

    console.print("\nNext steps:")
    console.print("  1. Edit config.yaml — fill in your LLM API key and Feishu credentials")
    console.print("  2. Run [bold]swarm chat[/bold] to test in CLI mode")
    console.print("  3. Run [bold]swarm ws[/bold] to start Feishu bot")


@app.command()
def validate(
    config_path: str = typer.Option("config.yaml", "--config", "-c"),
) -> None:
    """Validate a configuration file."""
    from swarm.config.loader import load_config
    try:
        config = load_config(config_path)
        console.print(f"[green]✓[/green] Config at {config_path} is valid")
        console.print(f"  Provider: {config.llm.provider}")
        console.print(f"  Model: {config.llm.model}")
        console.print(f"  Feishu App: {config.feishu.app_id}")
    except Exception as e:
        console.print(f"[red]✗[/red] Config validation failed: {e}")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
```

```python
# swarm/cli/chat.py
"""Interactive chat REPL using Rich + prompt_toolkit."""

from __future__ import annotations

import asyncio
from datetime import datetime

from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.patch_stdout import patch_stdout
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from swarm.agent.loop import AgentLoop
from swarm.bus.queue import MessageBus
from swarm.providers.base import LLMProvider
from swarm.session.manager import SessionManager
from pathlib import Path


class InteractiveChat:
    """Interactive chat interface for Swarm."""

    def __init__(self, provider: LLMProvider, session_name: str = "default"):
        self.provider = provider
        self.session_name = session_name
        self.console = Console()
        self.bus = MessageBus()
        self.sessions = SessionManager(Path.home() / ".swarm")
        self.loop = AgentLoop(
            bus=self.bus,
            provider=provider,
            workspace=Path.home() / ".swarm",
            sessions=self.sessions,
        )

    async def run(self) -> None:
        """Run the interactive chat loop."""
        from swarm import __logo__

        self.console.print(__logo__, style="bold yellow")
        self.console.print(f"🐝 Swarm Chat — session: {self.session_name}")
        self.console.print("Type /help for commands, /exit to quit\n")

        history_path = Path.home() / ".swarm" / "chat_history"
        history_path.parent.mkdir(parents=True, exist_ok=True)
        session = PromptSession(history=FileHistory(str(history_path)))

        session_key = f"cli:{self.session_name}"

        while True:
            try:
                with patch_stdout():
                    user_input = await session.prompt_async("你 > ")
            except (EOFError, KeyboardInterrupt):
                self.console.print("\nGoodbye! 🐝")
                break

            user_input = user_input.strip()
            if not user_input:
                continue

            if user_input.lower() in ("/exit", "/quit"):
                self.console.print("Goodbye! 🐝")
                break

            # Show thinking indicator
            self.console.print("[dim]🐝 thinking...[/dim]", end="\r")

            try:
                result = await self.loop.process_direct(
                    user_input,
                    session_key=session_key,
                )
            except Exception as e:
                self.console.print(f"[red]Error: {e}[/red]")
                continue

            self.console.print(" " * 30, end="\r")  # Clear thinking line

            if result and result.content:
                self.console.print(Panel(
                    Markdown(result.content),
                    title="🐝 Swarm",
                    border_style="yellow",
                ))
```

```python
# swarm/cli/stream.py
"""Terminal streaming renderer for real-time LLM output."""

from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown


class StreamRenderer:
    """Renders streaming LLM output in the terminal using Rich Live."""

    def __init__(self):
        self.console = Console()
        self._buffer = ""
        self._live: Live | None = None

    def __enter__(self):
        self._live = Live("", console=self.console, refresh_per_second=10)
        self._buffer = ""
        return self

    def __exit__(self, *args):
        if self._live:
            self._live.stop()

    def add(self, delta: str) -> None:
        """Add a streaming delta to the buffer."""
        self._buffer += delta

    def finalize(self) -> str:
        """Stop streaming and return the full content."""
        if self._live:
            self._live.stop()
        return self._buffer
```

```python
# swarm/cli/__init__.py
"""CLI module — interactive chat, streaming renderer, command line."""
```

- [ ] **Step 2: Commit**

```bash
git add swarm/cli/
git commit -m "feat: add CLI interface (swarm chat / ws / init / validate)"
```

---

### Task 15: Integration — Wire Everything Together

**Files:**
- Create: `swarm/tests/test_integration.py`
- Create: `swarm/tests/conftest.py`

- [ ] **Step 1: Create conftest.py with shared fixtures**

```python
# tests/conftest.py
import pytest
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from swarm.bus.queue import MessageBus
from swarm.agent.context import RequestContext
from swarm.providers.base import LLMResponse


@pytest.fixture
def temp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture
def bus():
    return MessageBus()


@pytest.fixture
def mock_provider():
    p = MagicMock()
    p.chat = AsyncMock(return_value=LLMResponse(content="Mock response", stop_reason="end_turn"))
    p.model = "gpt-4o"
    p.context_window = 128_000
    p.generation = MagicMock()
    p.generation.max_tokens = 4096
    return p


@pytest.fixture
def sample_ctx():
    return RequestContext(
        trace_id="test-trace",
        chat_id="test_chat",
        chat_type="p2p",
        user_id="test_user",
        message_id="test_msg",
    )
```

- [ ] **Step 2: Write integration test**

```python
# tests/test_integration.py
"""
Integration test: end-to-end message → AgentLoop → response pipeline.
Uses mock LLM provider — no real API calls.
"""

import asyncio
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from swarm.bus.queue import MessageBus, InboundMessage
from swarm.agent.loop import AgentLoop
from swarm.session.manager import SessionManager
from swarm.tools.registry import ToolRegistry
from swarm.providers.base import LLMResponse


class TestFullPipeline:
    @pytest.mark.asyncio
    async def test_simple_conversation_flow(self, temp_dir, mock_provider):
        """A complete message → process → response cycle."""
        bus = MessageBus()
        sessions = SessionManager(temp_dir)
        tools = ToolRegistry()

        loop = AgentLoop(
            bus=bus,
            provider=mock_provider,
            workspace=temp_dir,
            sessions=sessions,
            tools=tools,
        )

        mock_provider.chat = AsyncMock(return_value=LLMResponse(
            content="你好！有什么可以帮助你的？", stop_reason="end_turn"))

        # Send a message
        msg = InboundMessage(
            channel="feishu",
            sender_id="user_ou_001",
            chat_id="oc_test_chat",
            content="你好",
            metadata={"message_id": "msg_001", "chat_type": "p2p"},
        )
        await bus.publish_inbound(msg)

        # Process it
        result = await loop.process_direct("你好", session_key="feishu:oc_test_chat")
        assert result is not None
        assert "帮助" in result.content

    @pytest.mark.asyncio
    async def test_multi_user_isolation(self, temp_dir, mock_provider):
        """Different users get isolated session storage."""
        sessions = SessionManager(temp_dir)

        # User A
        s_a = sessions.get_or_create("feishu:chat_A")
        s_a.add_message("user", "A's message")
        sessions.save(s_a)

        # User B
        s_b = sessions.get_or_create("feishu:chat_B")
        s_b.add_message("user", "B's message")
        sessions.save(s_b)

        # Verify isolation
        a = sessions.get_or_create("feishu:chat_A")
        b = sessions.get_or_create("feishu:chat_B")
        assert a.messages[0]["content"] == "A's message"
        assert b.messages[0]["content"] == "B's message"

    @pytest.mark.asyncio
    async def test_concurrent_session_isolation(self, temp_dir, mock_provider):
        """Concurrent requests to different sessions don't interfere."""
        bus = MessageBus()
        sessions = SessionManager(temp_dir)

        loop = AgentLoop(
            bus=bus,
            provider=mock_provider,
            workspace=temp_dir,
            sessions=sessions,
        )

        call_count = 0

        async def side_effect(messages, tools=None, **kw):
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.01)
            return LLMResponse(
                content=f"Response {call_count}",
                stop_reason="end_turn",
            )

        mock_provider.chat = AsyncMock(side_effect=side_effect)

        # Send 3 concurrent requests to different sessions
        results = await asyncio.gather(
            loop.process_direct("A", session_key="feishu:chat_A"),
            loop.process_direct("B", session_key="feishu:chat_B"),
            loop.process_direct("C", session_key="feishu:chat_C"),
        )

        assert len(results) == 3
        contents = {r.content for r in results}
        assert len(contents) == 3  # All unique
```

- [ ] **Step 3: Run integration tests**

```bash
pytest tests/test_integration.py -v
```

- [ ] **Step 4: Commit**

```bash
git add tests/conftest.py tests/test_integration.py
git commit -m "test: add integration tests (full pipeline + isolation verification)"
```

---

### Task 16: Documentation & Project Polish

**Files:**
- Create: `swarm/README.md`
- Create: `swarm/README_ZH.md`
- Create: `swarm/LICENSE`
- Create: `swarm/CONTRIBUTING.md`
- Create: `swarm/CHANGELOG.md`
- Create: `.github/workflows/ci.yml`

- [ ] **Step 1: Create documentation files**

Write README.md (English), README_ZH.md (Chinese) based on the spec's project description, MIT LICENSE, CONTRIBUTING.md with conventional commits guide, CHANGELOG.md.

- [ ] **Step 2: Create CI workflow**

```yaml
# .github/workflows/ci.yml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.11", "3.12", "3.13"]

    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
      - name: Install dependencies
        run: |
          pip install -e ".[dev]"
      - name: Lint
        run: ruff check swarm/
      - name: Test
        run: pytest tests/ -v --cov=swarm --cov-report=term
```

- [ ] **Step 3: Full test suite run**

```bash
pytest tests/ -v --cov=swarm --cov-report=term
ruff check swarm/
```

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "docs: add README, LICENSE, CI workflow, and project polish"
```

---

## Execution Order

```
Phase 0: Foundation
  Task 0: Project Skeleton
  Task 1: Config System
  Task 2: Logging System
  Task 3: Message Bus
  Task 4: Utils Module

Phase 1: Providers
  Task 5: Provider Layer

Phase 2: Agent
  Task 6: Agent Context
  Task 7: Agent Runner
  Task 8: AgentLoop

Phase 3: Storage
  Task 9: Session Manager
  Task 10: Memory System

Phase 4: Capabilities
  Task 11: Tools System

Phase 5: Integration
  Task 12: Auth System (depends on Session)
  Task 13: Feishu Gateway (depends on Bus, Agent)
  Task 14: CLI (depends on Agent, Config)
  Task 15: Integration Tests

Phase 6: Polish
  Task 16: Documentation & CI
```

Tasks within a phase can run in parallel. Phases are sequential — each depends on the previous.

---

## Verification Checklist

After all tasks complete, verify:

- [ ] `pytest tests/ -v` — all tests pass
- [ ] `ruff check swarm/` — no linting errors
- [ ] `swarm validate` — config validation works
- [ ] `swarm chat` — CLI interactive mode starts
- [ ] `swarm ws` — WebSocket mode starts (requires feishu credentials)
- [ ] `swarm init` — config wizard creates config.yaml
- [ ] `swarm version` — version prints correctly
- [ ] `pytest tests/ -v --cov=swarm --cov-report=term` — coverage ≥ 80%
- [ ] 10 concurrent chat_id test passes without cross-contamination
- [ ] Token encryption roundtrip test passes
- [ ] AgentLoop state machine transitions all covered
- [ ] Message parsing covers all Feishu msg_types
