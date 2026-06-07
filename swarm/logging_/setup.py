"""structlog configuration for Swarm."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import structlog

from swarm.logging_.handlers import CompressingTimedRotatingFileHandler
from swarm.logging_.trace import get_trace_id


def _add_trace_id(_logger, _method_name, event_dict):
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
    """Configure structlog with file and console output."""
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)
    level_num = getattr(logging, level.upper(), logging.INFO)

    shared_processors = [
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        _add_trace_id,
    ]

    root_logger = logging.getLogger()
    root_logger.setLevel(level_num)
    for h in root_logger.handlers[:]:
        root_logger.removeHandler(h)

    if json_format:
        app_handler = CompressingTimedRotatingFileHandler(
            log_dir=str(log_path), retention_days=retention_days,
            log_name="swarm",
        )
        app_handler.setLevel(level_num)
        app_handler.setFormatter(logging.Formatter("%(message)s"))
        root_logger.addHandler(app_handler)

    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(level_num)
    console_handler.setFormatter(logging.Formatter("%(message)s"))
    root_logger.addHandler(console_handler)

    if error_separate:
        error_handler = CompressingTimedRotatingFileHandler(
            log_dir=str(log_path), retention_days=retention_days,
            log_name="swarm-error",
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(logging.Formatter("%(message)s"))
        root_logger.addHandler(error_handler)

    if audit_enabled:
        audit_handler = CompressingTimedRotatingFileHandler(
            log_dir=str(log_path), retention_days=retention_days * 2,
            log_name="audit",
        )
        audit_handler.setLevel(logging.INFO)
        audit_handler.setFormatter(logging.Formatter("%(message)s"))
        audit_logger = logging.getLogger("swarm.audit")
        audit_logger.addHandler(audit_handler)
        audit_logger.propagate = False

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
