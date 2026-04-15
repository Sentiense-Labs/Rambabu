"""
Logging middleware for Agno tools.

Wraps tool execution with logger.info entry/exit.
"""

from __future__ import annotations

import logging
import time
from typing import Callable

logger = logging.getLogger("agno.tools")


def with_logging(fn: Callable[..., str]) -> Callable[..., str]:
    """Decorator that logs tool entry, exit, and errors."""

    def wrapper(*_args, args=None, kwargs=None, **kw) -> str:
        final_args = args if args is not None else (_args if _args else ())
        final_kwargs = kwargs if kwargs is not None else kw
        tool_name = fn.__name__
        logger.info(
            f"[tool] {tool_name} called — args={final_args}, kwargs={final_kwargs}"
        )
        start = time.time()
        try:
            result = fn(*final_args, **final_kwargs)
            elapsed = time.time() - start
            preview = str(result)[:200].replace("\n", " | ")
            logger.info(f"[tool] {tool_name} ok in {elapsed:.2f}s — {preview}")
            return result
        except Exception as exc:
            elapsed = time.time() - start
            logger.warning(f"[tool] {tool_name} error after {elapsed:.2f}s — {exc}")
            raise

    wrapper.__name__ = fn.__name__
    wrapper.__doc__ = fn.__doc__
    return wrapper
