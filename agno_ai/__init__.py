"""agno_ai — Rover agent built on Agno.

Module-level hw singleton: set once at startup via set_hw().
Tools access it directly without needing run_context propagation.
"""

from agno_ai.types.context import HardwareContext

_hw: HardwareContext | None = None


def set_hw(hw: HardwareContext) -> None:
    global _hw
    _hw = hw


def get_hw() -> HardwareContext | None:
    return _hw
