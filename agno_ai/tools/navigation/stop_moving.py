from agno_ai.middleware.logging import with_logging
from agno_ai.middleware.timeout import with_timeout
from agno_ai.types.context import HardwareContext
from agno_ai import constants as C


def _get_hw(run_context=None) -> HardwareContext | None:
    if run_context is None:
        return None
    return run_context.session_state.get("hw")


@with_logging
@with_timeout(seconds=C.TIMEOUT_STOP_MOVING)
def stop_moving(run_context=None) -> str:
    """Halt all motor movement immediately."""
    hw = _get_hw(run_context)
    if hw is None or hw.movement_manager is None:
        return '{"status": "error", "message": "movement_manager not available"}'
    result = hw.movement_manager.stop()
    if hw.motor is not None:
        try:
            hw.motor.steer_center()
        except Exception:
            pass
    run_context.session_state.set("is_moving", False)
    run_context.session_state.set("direction", None)
    return str(result)
