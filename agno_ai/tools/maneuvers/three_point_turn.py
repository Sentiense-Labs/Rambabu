"""
three_point_turn — space-adaptive 180° heading flip.

Single-arc when front clearance >= 85cm, otherwise iterative N-point.
If currently pressed against obstacle (< 60cm), prepends a back disengage.
"""

from __future__ import annotations


from agno_ai import get_hw
from agno_ai.middleware.logging import with_logging
from agno_ai.middleware.timeout import with_timeout
from agno_ai.types.context import HardwareContext
from agno_ai import constants as C
from agno_ai.brain.maneuvers import (
    three_point_turn as _maneuver,
)


def _stop_motion(hw: HardwareContext) -> None:
    if hw.motor is not None:
        hw.motor.stop()
        try:
            hw.motor.steer_center()
        except Exception:
            pass


@with_logging
@with_timeout(seconds=C.TIMEOUT_THREE_POINT_TURN)
def three_point_turn(preferred_side: str = "right", run_context=None) -> str:
    """Execute a three-point turn to reverse direction in limited space."""
    if preferred_side not in ("left", "right"):
        return f'{{"status": "error", "message": "invalid preferred_side: {preferred_side}"}}'

    hw = get_hw()
    if hw is None:
        return '{"status": "error", "message": "no hardware context"}'

    _stop_motion(hw)

    try:
        result = _maneuver(hw, preferred_side=preferred_side)
        return str(result)
    except Exception as exc:
        _stop_motion(hw)
        return f'{{"status": "error", "message": "{exc}"}}'
