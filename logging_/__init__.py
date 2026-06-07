"""Logging system for Swarm — structlog + rotation + compression + audit."""

from logging_.setup import setup_logging
from logging_.trace import TraceContext, get_trace_id, new_trace_id, set_trace_id

__all__ = [
    "setup_logging",
    "TraceContext",
    "get_trace_id",
    "set_trace_id",
    "new_trace_id",
]
