"""Error classification and sanitation for tool execution.

Hermes pattern: tools must NEVER expose raw exceptions to the LLM.
All errors are classified (transient/rate_limit/auth/validation/not_found/internal)
and sanitized to remove sensitive information before being returned.
"""

from __future__ import annotations

import re
import time
from enum import Enum


class ErrorCategory(Enum):
    """Standard error categories for tool execution failures."""

    TRANSIENT = "transient"  # Temporary: network blip, timeout, retry
    RATE_LIMIT = "rate_limit"  # Rate limited: back off and retry
    AUTH = "auth"  # Authentication/authorization failure
    VALIDATION = "validation"  # Invalid input arguments
    NOT_FOUND = "not_found"  # Resource not found
    INTERNAL = "internal"  # Unexpected internal error


# Patterns that must never leak to LLM
_SENSITIVE_PATTERNS: list[tuple[str, str]] = [
    (r"sk-[a-zA-Z0-9]{20,}", "[API_KEY]"),
    (r"Bearer\s+[a-zA-Z0-9\-._~+/]+=*", "[AUTH_TOKEN]"),
    (r'api[_-]?key[=:]\s*["\']?[a-zA-Z0-9\-_]+["\']?', "api_key=[REDACTED]"),
    (r'token[=:]\s*["\']?[a-zA-Z0-9\-_.]+["\']?', "token=[REDACTED]"),
    (r"/home/\w+/", "/home/[USER]/"),
    (r"/Users/\w+/", "/Users/[USER]/"),
    (r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}", "[IP]"),
    (r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", "[EMAIL]"),
]


def classify_error(error: Exception) -> ErrorCategory:
    """Classify an exception into a standard error category."""
    error_type = type(error).__name__
    error_str = str(error).lower()

    # Rate limit indicators
    if any(kw in error_str for kw in ("rate limit", "too many requests", "429")):
        return ErrorCategory.RATE_LIMIT

    # Auth failures
    if any(
        kw in error_str
        for kw in (
            "unauthorized",
            "forbidden",
            "invalid api key",
            "auth",
            "401",
            "403",
        )
    ):
        return ErrorCategory.AUTH

    # Validation errors
    if any(
        kw in error_str
        for kw in (
            "validation",
            "invalid",
            "missing",
            "required",
            "bad request",
            "400",
        )
    ):
        return ErrorCategory.VALIDATION

    # Not found
    if any(kw in error_str for kw in ("not found", "404", "no such file")):
        return ErrorCategory.NOT_FOUND

    # Transient network errors
    transient_types = {
        "TimeoutError",
        "ConnectionError",
        "Timeout",
        "ReadError",
        "BrokenPipeError",
        "ConnectionResetError",
        "RemoteDisconnected",
    }
    if error_type in transient_types:
        return ErrorCategory.TRANSIENT
    if any(
        kw in error_str
        for kw in (
            "timeout",
            "connection",
            "broken pipe",
            "reset",
            "refused",
        )
    ):
        return ErrorCategory.TRANSIENT

    return ErrorCategory.INTERNAL


def sanitize_tool_error(error: Exception) -> str:
    """Clean tool error messages to remove sensitive information.

    Returns a safe string suitable for returning to the LLM.
    Max 500 characters to prevent context pollution.
    """
    message = str(error)
    for pattern, replacement in _SENSITIVE_PATTERNS:
        message = re.sub(pattern, replacement, message)
    if len(message) > 500:
        message = message[:497] + "..."
    return message


def is_retryable(error: Exception) -> bool:
    """Determine if an error is likely transient and worth retrying."""
    return classify_error(error) in (ErrorCategory.TRANSIENT, ErrorCategory.RATE_LIMIT)


def get_retry_delay(error: Exception, attempt: int) -> float:
    """Calculate retry delay with exponential backoff and jitter.

    Base 1s, capped at 60s, ±25% jitter.
    """
    base = 1.0
    delay = base * (2 ** (attempt - 1))
    capped = min(delay, 60.0)
    jitter = capped * 0.25 * (hash(str(time.time())) % 100 / 100 - 0.5)
    return max(0.1, capped + jitter)
