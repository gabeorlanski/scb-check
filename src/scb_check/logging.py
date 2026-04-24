"""Configure structured logging for `scb-check`."""

from __future__ import annotations

import logging
import sys
from typing import TYPE_CHECKING, cast

import structlog

if TYPE_CHECKING:
    from structlog.typing import FilteringBoundLogger


def _log_level(verbosity: int) -> int:
    levels = {
        0: logging.WARNING,
        1: logging.INFO,
    }
    return (
        logging.DEBUG
        if verbosity >= 2  # noqa: PLR2004
        else levels.get(verbosity, logging.WARNING)
    )


def configure_logging(verbosity: int) -> None:
    """Configure `structlog` and stdlib logging for CLI verbosity."""
    level = _log_level(verbosity)
    logging.basicConfig(
        format="%(message)s",
        level=level,
        stream=sys.stderr,
        force=True,
    )
    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="%H:%M:%S"),
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> FilteringBoundLogger:
    """Return a typed `structlog` logger for `name`."""
    return cast("FilteringBoundLogger", structlog.get_logger(name))
