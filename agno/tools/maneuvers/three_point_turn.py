"""
three_point_turn — space-adaptive 180° heading flip.

Single-arc when front clearance >= 85cm, otherwise iterative N-point.
If currently pressed against obstacle (< 60cm), prepends a back disengage.
"""

from __future__ import annotations


from agno.middleware.logging import with_logging
from agno.middleware.timeout import with_timeout
from agno.types.context import HardwareContext
from agno import constants as C
from brain.maneuvers import (
    three_point_turn as _maneuver,
)


def _get_hw(run_context=None) -> HardwareContext | None:
    if run_context is None:
        return None
    return run_context.session_state.get("hw")


def _stop_motion(hw: HardwareContext) -> None:
    if hw.movement_manager is not None:
        hw.movement_manager.stop()
    elif hw.motor is not None:
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

    hw = _get_hw(run_context)
    if hw is None:
        return '{"status": "error", "message": "no hardware context"}'

    _stop_motion(hw)

    try:
        result = _maneuver(hw, preferred_side=preferred_side)
        return str(result)
    except Exception as exc:
        _stop_motion(hw)
        return f'{{"status": "error", "message": "{exc}"}}'
