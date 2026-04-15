import time as _time

from agno_ai.middleware.logging import with_logging
from agno_ai.middleware.timeout import with_timeout
from agno_ai.types.context import HardwareContext
from agno_ai import constants as C

_DRIVE_SPEED = C.DRIVE_SPEED
_STEER_LOCK_SETTLE_S = C.STEER_LOCK_SETTLE_S
_CORRECTION_SECONDS = C._CORRECTION_SECONDS


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
@with_timeout(seconds=C.TIMEOUT_ALIGN_TO_PATH)
def align_to_path(
    drift_direction: str,
    correction_strength: str = "light",
    run_context=None,
) -> str:
    """Apply a brief steering correction to re-center on a path.
    drift_direction: which way you have drifted (steer OPPOSITE to correct).
    correction_strength: light=0.2s, medium=0.4s, strong=0.6s.
    """
    if drift_direction not in ("left", "right"):
        return f'{{"status": "error", "message": "invalid drift_direction: {drift_direction}"}}'

    seconds = _CORRECTION_SECONDS.get(correction_strength)
    if seconds is None:
        return f'{{"status": "error", "message": "invalid correction_strength: {correction_strength}"}}'

    hw = _get_hw(run_context)
    if hw is None or hw.motor is None:
        return '{"status": "error", "message": "motor not available"}'

    correction_side = "right" if drift_direction == "left" else "left"

    _stop_motion(hw)
    try:
        motor = hw.motor
        if correction_side == "left":
            motor.steer_left_hold()
        else:
            motor.steer_right_hold()
        _time.sleep(_STEER_LOCK_SETTLE_S)
        motor.front(_DRIVE_SPEED)
        _time.sleep(seconds)
        motor.stop()
        motor.front(_DRIVE_SPEED)
        _time.sleep(0.3)
        motor.stop()
        return str(
            {
                "status": "ok",
                "maneuver": "align_to_path",
                "drift_direction": drift_direction,
                "correction_side": correction_side,
                "correction_strength": correction_strength,
                "duration_s": round(seconds, 2),
            }
        )
    except Exception as exc:
        _stop_motion(hw)
        return f'{{"status": "error", "message": "{exc}"}}'
