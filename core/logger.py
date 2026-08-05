from __future__ import annotations

import logging
import time
from typing import Optional


DEFAULT_LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"


def configure_logging(level: int = logging.INFO, fmt: str = DEFAULT_LOG_FORMAT) -> None:
    """Configure root logging with UTC timestamps and a pipe-delimited format.

    Args:
        level: Logging level.
        fmt: Format string for log messages.
    """
    # Create handler and formatter manually to ensure UTC timestamps
    handler = logging.StreamHandler()
    formatter = logging.Formatter(fmt)
    # Use UTC for timestamps
    formatter.converter = time.gmtime  # type: ignore[attr-defined]
    handler.setFormatter(formatter)

    root = logging.getLogger()
    # Avoid duplicate handlers when configure_logging is called multiple times in tests
    if not any(isinstance(h, logging.StreamHandler) for h in root.handlers):
        root.addHandler(handler)
    root.setLevel(level)


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """Return a logger with the given name.

    Args:
        name: Optional logger name; None returns the root logger.
    """
    return logging.getLogger(name)
