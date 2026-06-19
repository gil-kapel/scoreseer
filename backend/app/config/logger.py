"""Shared loguru logger. Import `logger` everywhere — never use bare `print`.

Human-readable in development, JSON in production. Secrets must never be passed
to log calls; settings are logged only via `Settings.redacted()`.
"""

import sys

from loguru import logger

_configured = False


def configure_logging(level: str = "INFO", *, json_logs: bool = False) -> None:
    """Idempotently configure the global loguru sink."""
    global _configured
    if _configured:
        return
    logger.remove()
    if json_logs:
        logger.add(sys.stdout, level=level, serialize=True, backtrace=False, diagnose=False)
    else:
        logger.add(
            sys.stdout,
            level=level,
            colorize=True,
            backtrace=False,
            diagnose=False,
            format=(
                "<green>{time:HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | "
                "<cyan>{extra}</cyan> | <level>{message}</level>"
            ),
        )
    _configured = True


__all__ = ["logger", "configure_logging"]
