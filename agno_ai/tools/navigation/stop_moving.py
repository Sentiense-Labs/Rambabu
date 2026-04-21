from agno_ai import get_hw
from agno_ai.middleware.logging import with_logging
from agno_ai.middleware.timeout import with_timeout
from agno_ai import constants as C


@with_logging
@with_timeout(seconds=C.TIMEOUT_STOP_MOVING)
def stop_moving(run_context=None) -> str:
    """Halt all motor movement immediately."""
    hw = get_hw()
    if hw is None or hw.motor is None:
        return '{"status": "error", "message": "motor not available"}'
    result = hw.motor.stop()
    try:
        hw.motor.steer_center()
    except Exception:
        pass
    if run_context is not None and hasattr(run_context, "session_state"):
        run_context.session_state.set("is_moving", False)
        run_context.session_state.set("direction", None)
    return str(result)
