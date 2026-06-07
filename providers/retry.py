"""Retry logic for LLM API calls."""

from __future__ import annotations

import asyncio
import functools
import random
from dataclasses import dataclass
from typing import Callable

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class RetryConfig:
    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    jitter: bool = True


def _is_retryable(exc: Exception) -> bool:
    """Return True if the exception indicates a transient failure worth retrying.

    Retryable: network errors, timeouts, HTTP 5xx, HTTP 429 rate limits.
    Non-retryable: auth errors (401/403), bad requests (400), Value/Type errors.
    """
    # Network / timeout errors (stdlib + asyncio)
    if isinstance(exc, (asyncio.TimeoutError, ConnectionError, TimeoutError, OSError)):
        return True
    # OpenAI SDK: APIStatusError has status_code
    status = getattr(exc, 'status_code', None)
    if status is not None and (status >= 500 or status == 429):
        return True
    # Anthropic SDK: APIStatusError uses http_status
    http_status = getattr(exc, 'http_status', None)
    if http_status is not None and (http_status >= 500 or http_status == 429):
        return True
    # httpx / requests transport errors
    exc_name = type(exc).__name__
    if exc_name in ('ConnectError', 'ReadError', 'WriteError', 'RemoteProtocolError',
                     'ReadTimeout', 'ConnectTimeout', 'PoolTimeout'):
        return True
    return False


def async_retry(config: RetryConfig | None = None):
    """Decorator: retry async function on transient exceptions with exponential backoff.

    Only retries on network errors, timeouts, HTTP 5xx, and 429 rate limits.
    Non-transient errors (auth, bad request, validation) propagate immediately.
    """
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
                    if not _is_retryable(e):
                        raise
                    if attempt == config.max_retries:
                        logger.error(
                            "retry_exhausted",
                            func=func.__name__,
                            attempts=attempt + 1,
                            error=str(e),
                        )
                        raise
                    delay = min(config.base_delay * (2 ** attempt), config.max_delay)
                    if config.jitter:
                        delay *= 0.5 + random.random()
                    logger.warning(
                        "retry_attempt",
                        func=func.__name__,
                        attempt=attempt + 1,
                        max_retries=config.max_retries,
                        delay_s=round(delay, 2),
                        error_type=type(e).__name__,
                    )
                    await asyncio.sleep(delay)
            raise last_exception  # type: ignore
        return wrapper
    return decorator
