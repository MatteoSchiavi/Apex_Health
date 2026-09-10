"""Structured JSON logging to stdout (MASTER_SPEC §21)."""

import logging
import sys

from pythonjsonlogger.json import JsonFormatter

_LOGFIELD_WHITELIST = [
    "levelname",
    "name",
    "message",
    "asctime",
]


def configure_logging() -> None:
    """Route all relevant loggers through a single JSON handler on stdout."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter(_LOGFIELD_WHITELIST))

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.INFO)

    # uvicorn installs its own handlers/config after import; make everything
    # propagate to the root JSON handler instead of formatting separately.
    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(logger_name)
        logger.handlers = []
        logger.propagate = True
