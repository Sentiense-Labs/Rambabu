"""
move — discrete timed burst (non-blocking, max 2 seconds).

Returns immediately; motor runs in a background thread and auto-stops.
For sustained motion use move_cm() instead.
"""

from __future__ import annotations

import threading
import time

from agno_ai import get_hw
from agno_ai.middleware.logging import with_logging
from agno_ai.middleware.timeout import with_timeout
from agno_ai import constants as C

_DRIVE_SPEED = C.DRIVE_SPEED
_SAFETY_DISTANCE_CM = C.ZONE_CRITICAL_CM
_MAX_DURATION_S = 10.0

_VALID_DIRECTIONS = {
    "forward",
    "back",
    "left",
    "right",
    "stop",
    "back_left",
    "back_right",
}


@with_logging
@with_timeout(seconds=C.TIMEOUT_MOVE)
def move(direction: str, seconds: float = 0.5, run_context=None) -> str:
    """Drive the rover briefly (non-blocking). For distance-based moves, use move_cm() instead."""
    hw = get_hw()
    if direction not in _VALID_DIRECTIONS:
        return f'{{"status": "error", "message": "invalid direction: {direction}"}}'

    if direction == "stop":
        if hw and hw.motor:
            hw.motor.stop()
        return '{"status": "ok", "action": "stop"}'

    if hw is None or hw.motor is None:
        return '{"status": "error", "message": "motor not available"}'

    # Safety check for forward-family moves
    if direction in ("forward", "left", "right") and hw.ultrasonic is not None:
        dist = hw.ultrasonic.get_distance()
        if dist < _SAFETY_DISTANCE_CM:
            return str(
                {
                    "status": "blocked",
                    "reason": "obstacle_too_close",
                    "distance_cm": round(dist, 1),
                    "threshold_cm": _SAFETY_DISTANCE_CM,
                }
            )

    seconds = min(float(seconds), _MAX_DURATION_S)
    if seconds <= 0:
        return '{"status": "ok", "action": "no-op", "reason": "zero_duration"}'

    def _run() -> None:
        motor = hw.motor
        try:
            if direction == "forward":
                motor.front(_DRIVE_SPEED)
                time.sleep(seconds)
                motor.stop()
            elif direction == "back":
                motor.back(_DRIVE_SPEED)
                time.sleep(seconds)
                motor.stop()
            elif direction == "left":
                motor.steer_left_hold()
                motor.front(_DRIVE_SPEED)
                time.sleep(seconds)
                motor.stop()
                motor.steer_center()
            elif direction == "right":
                motor.steer_right_hold()
                motor.front(_DRIVE_SPEED)
                time.sleep(seconds)
                motor.stop()
                motor.steer_center()
            elif direction == "back_left":
                motor.steer_left_hold()
                motor.back(_DRIVE_SPEED)
                time.sleep(seconds)
                motor.stop()
                motor.steer_center()
            elif direction == "back_right":
                motor.steer_right_hold()
                motor.back(_DRIVE_SPEED)
                time.sleep(seconds)
                motor.stop()
                motor.steer_center()
        except Exception:
            try:
                motor.stop()
            except Exception:
                pass

    threading.Thread(target=_run, daemon=True).start()
    return (
        f'{{"status": "running", "direction": "{direction}", '
        f'"duration_s": {seconds}, "note": "Motor running in background."}}'
    )
