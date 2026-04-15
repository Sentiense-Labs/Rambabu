"""
move — legacy discrete timed burst.

For continuous motion prefer start_moving/stop_moving.
Hard-caps reverse directions at REVERSE_HARD_CAP_S (0.5s).
"""

from __future__ import annotations

from agno.middleware.logging import with_logging
from agno.middleware.timeout import with_timeout
from agno.types.context import HardwareContext
from agno import constants as C
import time

_DRIVE_SPEED = C.DRIVE_SPEED
_SAFETY_DISTANCE_CM = C.ZONE_CLOSE_CM


def _get_hw(run_context=None) -> HardwareContext | None:
    if run_context is None:
        return None
    return run_context.session_state.get("hw")


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
    """Drive the rover briefly. Forward/left/right are speed-safety-checked.
    Reverse directions are hard-capped at 0.5s (no rear sensor).
    """
    hw = _get_hw(run_context)
    if direction not in _VALID_DIRECTIONS:
        return f'{{"status": "error", "message": "invalid direction: {direction}"}}'

    if direction == "stop":
        if hw and hw.motor:
            hw.motor.stop()
        return '{"status": "ok", "action": "stop"}'

    if hw is None or hw.motor is None:
        return '{"status": "error", "message": "motor not available"}'

    try:
        # Safety check for forward directions
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

        # Cap reverse durations
        if direction in ("back", "back_left", "back_right"):
            seconds = min(seconds, C.REVERSE_HARD_CAP_S)

        if direction == "forward":
            hw.motor.front(_DRIVE_SPEED)
            time.sleep(seconds)
            hw.motor.stop()
            final = hw.ultrasonic.get_distance() if hw.ultrasonic else 0.0
            return str(
                {
                    "status": "ok",
                    "direction": "forward",
                    "duration_s": round(seconds, 2),
                    "final_distance_cm": round(final, 1),
                }
            )

        if direction == "back":
            hw.motor.back(_DRIVE_SPEED)
            time.sleep(seconds)
            hw.motor.stop()
            return str(
                {"status": "ok", "direction": "back", "duration_s": round(seconds, 2)}
            )

        if direction == "back_left":
            hw.motor.steer_left_hold()
            hw.motor.back(_DRIVE_SPEED)
            time.sleep(seconds)
            hw.motor.stop()
            hw.motor.steer_center()
            return str(
                {
                    "status": "ok",
                    "direction": "back_left",
                    "duration_s": round(seconds, 2),
                    "note": "front swung RIGHT, rear swung LEFT",
                }
            )

        if direction == "back_right":
            hw.motor.steer_right_hold()
            hw.motor.back(_DRIVE_SPEED)
            time.sleep(seconds)
            hw.motor.stop()
            hw.motor.steer_center()
            return str(
                {
                    "status": "ok",
                    "direction": "back_right",
                    "duration_s": round(seconds, 2),
                    "note": "front swung LEFT, rear swung RIGHT",
                }
            )

        if direction == "left":
            hw.motor.steer_left_hold()
            hw.motor.front(_DRIVE_SPEED)
            time.sleep(seconds)
            hw.motor.stop()
            hw.motor.steer_center()
            final = hw.ultrasonic.get_distance() if hw.ultrasonic else 0.0
            return str(
                {
                    "status": "ok",
                    "direction": "left",
                    "duration_s": round(seconds, 2),
                    "final_distance_cm": round(final, 1),
                }
            )

        if direction == "right":
            hw.motor.steer_right_hold()
            hw.motor.front(_DRIVE_SPEED)
            time.sleep(seconds)
            hw.motor.stop()
            hw.motor.steer_center()
            final = hw.ultrasonic.get_distance() if hw.ultrasonic else 0.0
            return str(
                {
                    "status": "ok",
                    "direction": "right",
                    "duration_s": round(seconds, 2),
                    "final_distance_cm": round(final, 1),
                }
            )

        return f'{{"status": "error", "message": "unhandled direction: {direction}"}}'

    except Exception as exc:
        if hw and hw.motor:
            hw.motor.stop()
        return str({"status": "error", "message": str(exc)})
