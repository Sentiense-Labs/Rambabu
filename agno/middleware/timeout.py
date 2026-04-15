"""
Timeout middleware for Agno tools.

Applies a timeout to tool execution using signal (Unix) or a background thread.
"""

from __future__ import annotations

import threading
from typing import Callable

_DEFAULT_TIMEOUT_S: float = 30.0


class ToolTimeoutError(Exception):
    """Raised when a tool exceeds its time limit."""

    pass


def with_timeout(
    seconds: float = _DEFAULT_TIMEOUT_S,
) -> Callable[[Callable[..., str]], Callable[..., str]]:
    """Decorator that kills tool execution after `seconds`."""

    def decorator(fn: Callable[..., str]) -> Callable[..., str]:
        def wrapper(*_args, args=None, kwargs=None, **kw) -> str:
            final_args = args if args is not None else (_args if _args else ())
            final_kwargs = kwargs if kwargs is not None else kw
            result = [None]
            error = [None]
            done = [False]

            def target():
                try:
                    result[0] = fn(*final_args, **final_kwargs)
                except Exception as e:
                    error[0] = e
                finally:
                    done[0] = True

            t = threading.Thread(target=target, daemon=True)
            t.start()
            t.join(timeout=seconds)

            if not done[0]:
                raise ToolTimeoutError(f"{fn.__name__} timed out after {seconds}s")

            if error[0] is not None:
                raise error[0]

            return result[0]

        wrapper.__name__ = fn.__name__
        wrapper.__doc__ = fn.__doc__
        return wrapper

    return decorator
