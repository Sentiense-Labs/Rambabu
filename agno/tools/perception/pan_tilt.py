from agno.middleware.logging import with_logging
from agno.middleware.timeout import with_timeout
from agno.types.context import HardwareContext
from agno import constants as C


_VALID_ACTIONS = {"pan_left", "pan_right", "tilt_up", "tilt_down", "center", "angles"}
_DEFAULT_DEGREES = 40


def _get_hw(run_context=None) -> HardwareContext | None:
    if run_context is None:
        return None
    return run_context.session_state.get("hw")


@with_logging
@with_timeout(seconds=C.TIMEOUT_PAN_TILT)
def pan_tilt(action: str, degrees: int = _DEFAULT_DEGREES, run_context=None) -> str:
    """Aim the camera: pan_left, pan_right, tilt_up, tilt_down, center, angles."""
    hw = _get_hw(run_context)
    if hw is None or hw.pan_tilt is None:
        return '{"status": "error", "message": "pan_tilt not available"}'
    if action not in _VALID_ACTIONS:
        return f'{{"status": "error", "message": "invalid action: {action}"}}'

    try:
        pt = hw.pan_tilt
        if action == "pan_left":
            result = pt.pan_left(degrees)
        elif action == "pan_right":
            result = pt.pan_right(degrees)
        elif action == "tilt_up":
            result = pt.tilt_up(degrees)
        elif action == "tilt_down":
            result = pt.tilt_down(degrees)
        elif action == "center":
            result = pt.center()
        elif action == "angles":
            result = pt.get_angles()
        else:
            result = {"status": "error", "message": f"unhandled action: {action}"}
        return str(result)
    except Exception as exc:
        return f'{{"status": "error", "message": "{exc}"}}'
