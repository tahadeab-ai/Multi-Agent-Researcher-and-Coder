"""structlog configuration for PHOENIX.

Provides structured JSON logging in CI/production and
colored human-readable logs in interactive terminals.

Usage:
    from src.logging_config import get_logger
    log = get_logger(__name__)
    log.info("agent_step", agent="Coder", turn=3, tokens=100)
"""

from __future__ import annotations

import logging
import sys

import structlog


def configure_logging(json_logs: bool = False) -> None:
    """Configure structlog for the application.

    Args:
        json_logs: If True, output newline-delimited JSON (for CI/prod).
                   If False, output human-readable colored logs.
    """
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    if json_logs:
        renderer: structlog.types.Processor = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer()

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.DEBUG),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Return a structlog logger bound to the given name."""
    return structlog.get_logger(name)  # type: ignore[return-value]
