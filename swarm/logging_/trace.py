"""Trace ID management for request-level tracing through all subsystems."""

from __future__ import annotations

import uuid
from contextvars import ContextVar

_trace_id_var: ContextVar[str | None] = ContextVar("trace_id", default=None)


class TraceContext:
    """Context manager for trace ID propagation."""

    def set(self, trace_id: str | None = None) -> str:
        tid = trace_id or str(uuid.uuid4())
        _trace_id_var.set(tid)
        return tid

    def get(self) -> str | None:
        return _trace_id_var.get()

    def ensure(self) -> str:
        tid = _trace_id_var.get()
        if tid is None:
            tid = str(uuid.uuid4())
            _trace_id_var.set(tid)
        return tid


def get_trace_id() -> str | None:
    return _trace_id_var.get()


def set_trace_id(trace_id: str) -> None:
    _trace_id_var.set(trace_id)


def new_trace_id() -> str:
    tid = str(uuid.uuid4())
    _trace_id_var.set(tid)
    return tid
