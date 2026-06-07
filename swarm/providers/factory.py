"""Provider factory: create LLMProvider from configuration."""

from __future__ import annotations

from swarm.config.schema import LLMConfig
from swarm.providers.base import LLMProvider


def make_provider(config: LLMConfig) -> LLMProvider:
    """Create a provider instance from configuration, with optional fallback chain."""
    primary = _make_single_provider(config)

    # Build fallback chain if configured
    if config.fallback:
        fallbacks = []
        for fb_cfg in config.fallback:
            fb_config = config.model_copy(update=fb_cfg)
            fallbacks.append(_make_single_provider(fb_config))
        from swarm.providers.fallback import FallbackProvider
        return FallbackProvider([primary] + fallbacks)

    return primary


def _make_single_provider(config: LLMConfig) -> LLMProvider:
    """Create a single provider from LLMConfig (without fallback)."""
    provider_type = config.provider

    if provider_type in ("openai", "custom"):
        from swarm.providers.openai_compat import OpenAICompatProvider
        return OpenAICompatProvider(
            api_key=config.api_key, base_url=config.base_url,
            model=config.model, max_tokens=config.max_tokens,
            temperature=config.temperature,
        )
    elif provider_type == "anthropic":
        from swarm.providers.anthropic import AnthropicProvider
        return AnthropicProvider(
            api_key=config.api_key, base_url=config.base_url or None,
            model=config.model, max_tokens=config.max_tokens,
            temperature=config.temperature,
        )
    else:
        raise ValueError(f"Unknown provider type: {provider_type}")
