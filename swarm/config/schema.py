"""Pydantic v2 configuration schema for Swarm."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class LLMConfig(BaseModel):
    """LLM provider configuration."""

    provider: Literal["openai", "anthropic", "custom"] = "anthropic"
    base_url: str = "https://api.deepseek.com/anthropic"
    api_key: str = ""
    model: str = "deepseek-v4-pro"
    max_tokens: int = Field(default=4096, ge=1)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    fallback: list[dict] = Field(default_factory=list)


class FeishuConfig(BaseModel):
    """Feishu/Lark platform configuration."""

    app_id: str = ""
    app_secret: str = ""
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

    llm: LLMConfig = Field(default_factory=LLMConfig)
    feishu: FeishuConfig = Field(default_factory=FeishuConfig)
    auth: AuthConfig = Field(default_factory=AuthConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    cron: CronConfig = Field(default_factory=CronConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    tools: ToolsConfig = Field(default_factory=ToolsConfig)
