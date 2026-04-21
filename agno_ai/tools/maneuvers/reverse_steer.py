import time as _time

from agno_ai import get_hw
from agno_ai.middleware.logging import with_logging
from agno_ai.middleware.timeout import with_timeout
from agno_ai.types.context import HardwareContext
from agno_ai import constants as C

_DRIVE_SPEED = C.DRIVE_SPEED
_STEER_LOCK_SETTLE_S = C.STEER_LOCK_SETTLE_S
_REVERSE_MAX_S = 8.0


def _stop_motion(hw: HardwareContext) -> None:
    if hw.motor is not None:
        hw.motor.stop()
        try:
            hw.motor.steer_center()
        except Exception:
            pass


@with_logging
@with_timeout(seconds=C.TIMEOUT_REVERSE_STEER)
def reverse_steer(steer_direction: str, seconds: float = 0.4, run_context=None) -> str:
    """Reverse with steering bias. In reverse, left steer swings the FRONT
    right and rear left (opposite of forward).
    """
    if steer_direction not in ("left", "right"):
        return f'{{"status": "error", "message": "invalid steer_direction: {steer_direction}"}}'

    hw = get_hw()
    if hw is None or hw.motor is None:
        return '{"status": "error", "message": "motor not available"}'

    seconds = max(0.05, min(float(seconds), _REVERSE_MAX_S))
    note = (
        "front swung RIGHT, rear swung LEFT"
        if steer_direction == "left"
        else "front swung LEFT, rear swung RIGHT"
    )

    _stop_motion(hw)
    try:
        motor = hw.motor
        if steer_direction == "left":
            motor.steer_left_hold()
        else:
            motor.steer_right_hold()
        _time.sleep(_STEER_LOCK_SETTLE_S)
        motor.back(_DRIVE_SPEED)
        _time.sleep(seconds)
        motor.stop()
        motor.steer_center()
        return str(
            {
                "status": "ok",
                "maneuver": "reverse_steer",
                "steer_direction": steer_direction,
                "duration_s": round(seconds, 2),
                "note": note,
            }
        )
    except Exception as exc:
        _stop_motion(hw)
        return f'{{"status": "error", "message": "{exc}"}}'
